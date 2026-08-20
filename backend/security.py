"""Security utilities for authentication, password hashing, and JWT management."""

import os
import re
import uuid
from datetime import datetime, timedelta

import bcrypt
from jose import jwt, JWTError

from backend.database import get_db

# JWT configuration
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Bcrypt work factor
BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    """Hash a password using bcrypt with work factor 12."""
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain text password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(username: str, role: str, first_time: bool) -> str:
    """Create a JWT access token with 60-minute expiry and unique jti.

    Args:
        username: The user's username (stored as 'sub' claim).
        role: The user's role (e.g., 'Admin', 'L1_User').
        first_time: Whether this is the user's first login (password change required).

    Returns:
        Encoded JWT token string.
    """
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "role": role,
        "first_time": first_time,
        "jti": str(uuid.uuid4()),
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token.

    Args:
        token: The encoded JWT token string.

    Returns:
        The decoded token payload as a dictionary.

    Raises:
        JWTError: If the token is invalid, expired, or cannot be decoded.
    """
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


def validate_password_policy(password: str) -> bool:
    """Validate that a password meets the security policy requirements.

    Policy: minimum 8 characters, at least one uppercase letter,
    one lowercase letter, one digit, and one special character.

    Args:
        password: The password string to validate.

    Returns:
        True if password meets all policy requirements, False otherwise.
    """
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    if not re.search(r"[^A-Za-z0-9]", password):
        return False
    return True


def generate_reset_token() -> str:
    """Generate a unique one-time reset token.

    Returns:
        A UUID4 string suitable for use as a password reset token.
    """
    return str(uuid.uuid4())


# Rate limiter configuration
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW_MINUTES = 15


class RateLimiter:
    """Login rate limiter that tracks failed attempts per username.

    Uses the login_attempts database table to enforce a rolling window
    of failed attempts. After 5 failed attempts within 15 minutes,
    subsequent login attempts are rejected until the window expires.
    """

    async def is_locked(self, username: str) -> bool:
        """Check if a username is locked out due to too many failed attempts.

        Args:
            username: The username to check.

        Returns:
            True if the user has >= 5 failed attempts in the last 15 minutes.
        """
        window_start = (
            datetime.utcnow() - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)
        ).strftime("%Y-%m-%d %H:%M:%S")

        async with get_db() as db:
            cursor = await db.execute(
                """
                SELECT COUNT(*) as cnt FROM login_attempts
                WHERE username = ? AND success = 0 AND attempted_at > ?
                """,
                (username, window_start),
            )
            row = await cursor.fetchone()
            count = row[0] if row else 0
            return count >= RATE_LIMIT_MAX_ATTEMPTS

    async def record_attempt(self, username: str, success: bool) -> None:
        """Record a login attempt in the database.

        Args:
            username: The username that attempted login.
            success: Whether the attempt was successful.
        """
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO login_attempts (username, attempted_at, success)
                VALUES (?, datetime('now'), ?)
                """,
                (username, 1 if success else 0),
            )
            await db.commit()

    async def reset(self, username: str) -> None:
        """Clear failed login attempts for a username (called on successful login).

        Args:
            username: The username to reset attempts for.
        """
        async with get_db() as db:
            await db.execute(
                """
                DELETE FROM login_attempts
                WHERE username = ? AND success = 0
                """,
                (username,),
            )
            await db.commit()
