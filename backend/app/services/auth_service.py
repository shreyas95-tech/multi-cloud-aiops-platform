"""Authentication service: password hashing, validation, and user management.

Provides bcrypt-based password hashing (cost factor 12), password strength
validation, and user registration/login logic.
"""

import re
from datetime import datetime, timezone

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


# --- Constants ---

BCRYPT_COST_FACTOR = 12
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

# Password must contain at least one of each:
_UPPERCASE_RE = re.compile(r"[A-Z]")
_LOWERCASE_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"\d")
_SPECIAL_RE = re.compile(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]")


# --- Password Utilities ---


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt with cost factor 12.

    Args:
        plain_password: The plaintext password to hash.

    Returns:
        The bcrypt hash as a string.
    """
    salt = bcrypt.gensalt(rounds=BCRYPT_COST_FACTOR)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Args:
        plain_password: The plaintext password to check.
        password_hash: The stored bcrypt hash.

    Returns:
        True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        password_hash.encode("utf-8"),
    )


def validate_password_strength(password: str) -> list[str]:
    """Validate password meets strength requirements.

    Requirements (Req 6.7):
    - Between 8 and 128 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Args:
        password: The password to validate.

    Returns:
        A list of validation error messages. Empty list means valid.
    """
    errors: list[str] = []

    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        errors.append(
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters long."
        )
    if not _UPPERCASE_RE.search(password):
        errors.append("Password must contain at least one uppercase letter.")
    if not _LOWERCASE_RE.search(password):
        errors.append("Password must contain at least one lowercase letter.")
    if not _DIGIT_RE.search(password):
        errors.append("Password must contain at least one digit.")
    if not _SPECIAL_RE.search(password):
        errors.append("Password must contain at least one special character.")

    return errors


# --- User Registration ---


async def register_user(
    db: AsyncSession,
    username: str,
    email: str,
    password: str,
) -> tuple[User | None, list[str]]:
    """Register a new user account.

    Validates password strength, checks for duplicate username/email,
    hashes the password, and creates the user record.

    Args:
        db: Async database session.
        username: Desired username.
        email: User email address.
        password: Plaintext password (will be hashed).

    Returns:
        A tuple of (User, []) on success, or (None, [errors]) on failure.
    """
    # Validate password strength
    password_errors = validate_password_strength(password)
    if password_errors:
        return None, password_errors

    # Check for existing username
    existing_user = await db.execute(
        select(User).where(User.username == username)
    )
    if existing_user.scalar_one_or_none() is not None:
        return None, ["Username is already taken."]

    # Check for existing email
    existing_email = await db.execute(
        select(User).where(User.email == email)
    )
    if existing_email.scalar_one_or_none() is not None:
        return None, ["Email address is already registered."]

    # Create the user
    hashed = hash_password(password)
    user = User(
        username=username,
        email=email.lower().strip(),
        password_hash=hashed,
        failed_login_attempts=0,
        last_active=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()

    return user, []
