"""Authentication API endpoints: registration, login, session management."""

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
import redis
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth_service import (
    hash_password,
    verify_password,
    validate_password_strength,
    register_user,
)


router = APIRouter(prefix="/auth", tags=["authentication"])

# --- JWT Configuration ---

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change-this-to-a-secure-random-string")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
)

# --- Redis for rate limiting ---

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis | None:
    """Get or create a Redis client for rate limiting. Returns None if unavailable."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            _redis_client.ping()
        except Exception:
            _redis_client = None
    return _redis_client


# --- Rate limiting constants ---

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 15 * 60  # 15 minutes
LOCKOUT_DURATION_SECONDS = 15 * 60  # 15 minutes

# --- Session inactivity ---

SESSION_INACTIVITY_MINUTES = 30


# --- Request/Response schemas ---


class RegisterRequest(BaseModel):
    """User registration request body."""

    username: str = Field(min_length=3, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RegisterResponse(BaseModel):
    """User registration response."""

    id: str
    username: str
    email: str
    message: str = "Registration successful."


class LoginRequest(BaseModel):
    """User login request body."""

    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response with JWT token."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    must_reset_password: bool = False


class UserResponse(BaseModel):
    """Current user info response."""

    id: str
    username: str
    email: str
    role: str
    group_id: str | None = None
    group_name: str | None = None
    must_reset_password: bool = False


# --- Helper Functions ---


def create_access_token(user_id: str, username: str) -> tuple[str, datetime]:
    """Create a JWT access token.

    Returns:
        Tuple of (token_string, expiry_datetime).
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "username": username,
        "iat": now,
        "exp": expires,
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token, expires


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT access token.

    Returns:
        The decoded payload dict or None if invalid/expired.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def _get_lockout_key(username: str) -> str:
    """Redis key for tracking failed login attempts."""
    return f"auth:lockout:{username}"


def _is_account_locked(username: str) -> bool:
    """Check if account is currently locked due to too many failed attempts."""
    r = get_redis()
    if r is None:
        return False  # No Redis = no rate limiting in dev
    try:
        key = _get_lockout_key(username)
        attempts = r.get(key)
        if attempts is not None and int(attempts) >= MAX_FAILED_ATTEMPTS:
            return True
    except Exception:
        pass
    return False


def _record_failed_attempt(username: str) -> int:
    """Record a failed login attempt. Returns the new attempt count."""
    r = get_redis()
    if r is None:
        return 0  # No Redis = no tracking in dev
    try:
        key = _get_lockout_key(username)
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, LOCKOUT_WINDOW_SECONDS)
        results = pipe.execute()
        return results[0]
    except Exception:
        return 0


def _clear_failed_attempts(username: str) -> None:
    """Clear failed login attempts after successful login."""
    r = get_redis()
    if r is None:
        return
    try:
        key = _get_lockout_key(username)
        r.delete(key)
    except Exception:
        pass


# --- Dependency: Get current user from JWT ---


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency that extracts and validates the current user from JWT.

    Also checks session inactivity (30 minutes). Updates last_active on success.
    Raises HTTPException 401 if not authenticated or session expired.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.split(" ", 1)[1]
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Check session inactivity
    if user.last_active:
        inactivity_cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=SESSION_INACTIVITY_MINUTES
        )
        # Ensure timezone-aware comparison (SQLite stores naive datetimes)
        last_active = user.last_active
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=timezone.utc)
        if last_active < inactivity_cutoff:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired due to inactivity",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Update last_active timestamp
    user.last_active = datetime.now(timezone.utc)
    await db.flush()

    return user


# --- Endpoints ---


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """Register a new user account.

    The first user registered becomes an admin. After that, only admins
    can create users via /api/admin/users.
    """
    # Check if any users exist - first user becomes admin
    user_count_result = await db.execute(select(User))
    existing_users = user_count_result.scalars().all()

    if len(existing_users) > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled. Contact an admin to create your account.",
        )

    # First user - create as admin
    user, errors = await register_user(
        db=db,
        username=body.username,
        email=body.email,
        password=body.password,
    )
    if errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=errors)

    # Make first user an admin
    user.role = "admin"
    user.must_reset_password = False
    await db.flush()

    return RegisterResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate user and return JWT token.

    Uses generic error messages (Req 6.2). Implements rate limiting with
    account lockout after 5 failed attempts in 15 minutes (Req 6.3).
    """
    # Check if account is locked
    if _is_account_locked(body.username):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account is temporarily locked due to too many failed login attempts. Please try again in 15 minutes.",
        )

    # Lookup user by username
    result = await db.execute(
        select(User).where(User.username == body.username)
    )
    user = result.scalar_one_or_none()

    # Generic error message for invalid credentials (Req 6.2)
    credentials_error = "The credentials provided are incorrect."

    if user is None:
        # Still record attempt to avoid timing attacks revealing username existence
        _record_failed_attempt(body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=credentials_error,
        )

    # Verify password
    if not verify_password(body.password, user.password_hash):
        attempts = _record_failed_attempt(body.username)
        if attempts >= MAX_FAILED_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Account is temporarily locked due to too many failed login attempts. Please try again in 15 minutes.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=credentials_error,
        )

    # Successful login - clear failed attempts
    _clear_failed_attempts(body.username)

    # Update last_active
    user.last_active = datetime.now(timezone.utc)
    user.failed_login_attempts = 0
    await db.flush()

    # Create JWT token
    token, expires = create_access_token(str(user.id), user.username)
    expires_in = int((expires - datetime.now(timezone.utc)).total_seconds())

    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        must_reset_password=user.must_reset_password,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Get current authenticated user info."""
    group_name = None
    if current_user.group_id:
        from app.models.group import Group
        g_result = await db.execute(select(Group).where(Group.id == current_user.group_id))
        g = g_result.scalar_one_or_none()
        group_name = g.name if g else None

    return UserResponse(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        group_id=str(current_user.group_id) if current_user.group_id else None,
        group_name=group_name,
        must_reset_password=current_user.must_reset_password,
    )


# --- Password Reset ---


class ResetPasswordRequest(BaseModel):
    """Password reset request - uses email to identify account."""

    email: EmailStr
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reset password for an account by email.

    For local development use. In production, this would require
    email verification with a reset token.
    """
    # Find user by email
    result = await db.execute(
        select(User).where(User.email == body.email)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with that email address.",
        )

    # Validate new password strength
    from app.services.auth_service import validate_password_strength, hash_password

    errors = validate_password_strength(body.new_password)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=errors,
        )

    # Update password
    user.password_hash = hash_password(body.new_password)
    user.must_reset_password = False
    await db.flush()

    return {"message": "Password reset successful. You can now log in with your new password."}
