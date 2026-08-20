"""User management routes (Admin only).

Provides endpoints for creating users and listing all users.
Both endpoints are protected by Admin role and require completed password change.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth_models import CreateUserRequest, UserResponse
from backend.database import get_pool
from backend.security import hash_password, validate_password_policy
from backend.api.middleware.rbac import require_role, require_not_first_time
from backend.api.main import success_response

router = APIRouter(prefix="/api", tags=["users"])


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("Admin")), Depends(require_not_first_time())],
)
async def create_user(body: CreateUserRequest):
    """Create a new user with a temporary password.

    The user is created with first_time_flag=true, requiring them to change
    their password on first login.

    Args:
        body: CreateUserRequest with username, password, and role.

    Returns:
        201 with the created user info in UserResponse format.

    Raises:
        400: Password does not meet policy requirements.
        409: Username already exists.
    """
    # Validate password meets policy
    if not validate_password_policy(body.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password does not meet policy requirements: minimum 8 characters, "
            "at least one uppercase, one lowercase, one digit, and one special character",
        )

    # Hash the password
    password_hash = hash_password(body.password)

    # Insert into users table
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Check if username already exists
        existing = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1", body.username
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )

        await conn.execute(
            "INSERT INTO users (username, password_hash, role, first_time_flag) VALUES ($1, $2, $3, TRUE)",
            body.username, password_hash, body.role
        )

        # Fetch the created user to get the created_at timestamp
        row = await conn.fetchrow(
            "SELECT username, role, created_at FROM users WHERE username = $1",
            body.username
        )

    user = UserResponse(
        username=row["username"],
        role=row["role"],
        created_at=str(row["created_at"]),
    )
    return success_response(user.model_dump())


@router.get(
    "/users",
    dependencies=[Depends(require_role("Admin")), Depends(require_not_first_time())],
)
async def list_users():
    """List all users with username, role, and created_at.

    Returns:
        List of UserResponse objects wrapped in success envelope.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT username, role, created_at FROM users ORDER BY created_at DESC"
        )

    users = [
        UserResponse(
            username=row["username"],
            role=row["role"],
            created_at=str(row["created_at"]),
        ).model_dump()
        for row in rows
    ]
    return success_response(users)
