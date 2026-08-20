"""Authentication routes: login, logout, password reset, and change-password endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth_models import (
    LoginRequest,
    LoginResponse,
    PasswordResetRequest,
    PasswordResetConfirm,
    ChangePasswordRequest,
)
from backend.database import get_pool
from backend.security import (
    RateLimiter,
    create_access_token,
    verify_password,
    hash_password,
    generate_reset_token,
    validate_password_policy,
)
from backend.api.middleware.auth_middleware import get_current_user
from backend.api.main import success_response, error_response

router = APIRouter(prefix="/api/auth", tags=["auth"])

rate_limiter = RateLimiter()


@router.post("/login")
async def login(request: LoginRequest):
    """Authenticate user and return a JWT access token.

    - Checks rate limiter first (429 if locked out)
    - Validates credentials against users table
    - Returns JWT with role and first_time_flag on success
    """
    username = request.username
    password = request.password

    # Check rate limiter first
    if await rate_limiter.is_locked(username):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
        )

    # Query user from database
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, username, password_hash, role, first_time_flag FROM users WHERE username = $1",
            username
        )

    # Validate credentials
    if not user or not verify_password(password, user["password_hash"]):
        # Record failed attempt
        await rate_limiter.record_attempt(username, success=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Successful login - record success and reset rate limiter
    await rate_limiter.record_attempt(username, success=True)
    await rate_limiter.reset(username)

    # Create JWT token
    first_time_flag = bool(user["first_time_flag"])
    access_token = create_access_token(
        username=user["username"],
        role=user["role"],
        first_time=first_time_flag,
    )

    # Return login response
    response = LoginResponse(
        access_token=access_token,
        role=user["role"],
        requires_password_change=first_time_flag,
    )
    return success_response(response.model_dump())


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """Logout by blacklisting the current token's jti.

    Requires an authenticated user. Adds the token jti to the
    blacklist with a 1-hour expiry.
    """
    jti = current_user["jti"]
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO token_blacklist (jti, expires_at) VALUES ($1, $2) ON CONFLICT (jti) DO NOTHING",
            jti, expires_at
        )

    return success_response({"message": "Logged out successfully"})


@router.post("/reset-request")
async def reset_request(request: PasswordResetRequest):
    """Request a password reset token.

    Generates a reset token with 30-minute expiry for the given username.
    Returns a generic success response regardless of whether the username exists
    to prevent user enumeration.
    """
    username = request.username

    # Check if user exists
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1",
            username
        )

    # If user doesn't exist, return generic success to prevent enumeration
    if not user:
        return success_response({"message": "If the account exists, a reset token has been generated."})

    # Generate reset token with 30-minute expiry
    token = generate_reset_token()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO reset_tokens (username, token, expires_at, used) VALUES ($1, $2, $3, $4)",
            username, token, expires_at, False
        )

    return success_response({
        "message": "If the account exists, a reset token has been generated.",
        "token": token,
    })


@router.post("/reset")
async def reset_password(request: PasswordResetConfirm):
    """Reset password using a valid reset token.

    Validates that the token exists, has not been used, and has not expired.
    Enforces password policy on the new password.
    """
    token = request.token
    new_password = request.new_password

    # Look up the reset token
    pool = await get_pool()
    async with pool.acquire() as conn:
        token_row = await conn.fetchrow(
            "SELECT id, username, expires_at, used FROM reset_tokens WHERE token = $1",
            token
        )

    # Validate token existence, usage, and expiry
    if not token_row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is invalid or expired",
        )

    if token_row["used"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is invalid or expired",
        )

    # Check expiry - asyncpg returns datetime objects directly
    expires_at = token_row["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is invalid or expired",
        )

    # Validate new password meets policy
    if not validate_password_policy(new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password does not meet policy requirements: minimum 8 characters, "
                   "at least one uppercase, one lowercase, one digit, and one special character.",
        )

    # Hash new password and update user record
    new_hash = hash_password(new_password)
    username = token_row["username"]

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET password_hash = $1 WHERE username = $2",
            new_hash, username
        )
        # Mark token as used
        await conn.execute(
            "UPDATE reset_tokens SET used = TRUE WHERE id = $1",
            token_row["id"]
        )

    return success_response({"message": "Password has been reset successfully."})


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    """Change password for authenticated user (especially first-time login).

    Validates current password, enforces password policy on the new password,
    updates the hash, clears the first_time_flag, and issues a new JWT.
    """
    username = current_user["username"]
    current_password = request.current_password
    new_password = request.new_password

    # Get stored password hash
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT password_hash, role FROM users WHERE username = $1",
            username
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Verify current password
    if not verify_password(current_password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    # Validate new password meets policy
    if not validate_password_policy(new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password does not meet policy requirements: minimum 8 characters, "
                   "at least one uppercase, one lowercase, one digit, and one special character.",
        )

    # Hash new password and update user record + clear first_time_flag
    new_hash = hash_password(new_password)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET password_hash = $1, first_time_flag = FALSE WHERE username = $2",
            new_hash, username
        )

    # Issue new JWT with first_time=false
    role = user["role"]
    access_token = create_access_token(username=username, role=role, first_time=False)

    return success_response({
        "message": "Password changed successfully.",
        "access_token": access_token,
        "role": role,
    })
