"""Admin API endpoints: user creation, group management.

Only accessible by users with role='admin'.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.group import Group
from app.services.auth_service import hash_password, validate_password_strength

router = APIRouter(prefix="/admin", tags=["admin"])


# --- Admin Guard ---


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency that ensures the current user is an admin."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user


# --- Schemas ---


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="user", pattern="^(admin|user)$")
    group_id: str | None = None


class CreateUserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    group_id: str | None
    must_reset_password: bool


class UserListResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    group_name: str | None
    must_reset_password: bool
    last_active: str | None


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class GroupResponse(BaseModel):
    id: str
    name: str
    description: str | None
    member_count: int


# --- User Management Endpoints ---


@router.post("/users", response_model=CreateUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> CreateUserResponse:
    """Create a new user (admin only).

    The user will be forced to reset their password on first login.
    """
    # Validate password
    errors = validate_password_strength(body.password)
    if errors:
        raise HTTPException(status_code=400, detail=errors)

    # Check duplicates
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken.")

    existing_email = await db.execute(select(User).where(User.email == body.email))
    if existing_email.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered.")

    # Validate group if provided
    group_id = None
    if body.group_id:
        group_result = await db.execute(select(Group).where(Group.id == body.group_id))
        if group_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Group not found.")
        group_id = body.group_id

    # Create user with must_reset_password=True
    user = User(
        username=body.username,
        email=body.email.lower().strip(),
        password_hash=hash_password(body.password),
        role=body.role,
        group_id=group_id,
        must_reset_password=True,
        failed_login_attempts=0,
        last_active=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()

    return CreateUserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
        group_id=str(user.group_id) if user.group_id else None,
        must_reset_password=user.must_reset_password,
    )


@router.get("/users")
async def list_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all users (admin only)."""
    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    response = []
    for u in users:
        # Get group name
        group_name = None
        if u.group_id:
            g_result = await db.execute(select(Group).where(Group.id == u.group_id))
            g = g_result.scalar_one_or_none()
            group_name = g.name if g else None

        response.append({
            "id": str(u.id),
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "group_name": group_name,
            "group_id": str(u.group_id) if u.group_id else None,
            "must_reset_password": u.must_reset_password,
            "last_active": u.last_active.isoformat() if u.last_active else None,
        })

    return {"users": response, "count": len(response)}


# --- Group Management Endpoints ---


@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: CreateGroupRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> GroupResponse:
    """Create a new group (admin only)."""
    # Check duplicate name
    existing = await db.execute(select(Group).where(Group.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Group name already exists.")

    group = Group(name=body.name, description=body.description)
    db.add(group)
    await db.flush()

    return GroupResponse(id=str(group.id), name=group.name, description=group.description, member_count=0)


@router.get("/groups")
async def list_groups(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all groups (admin only)."""
    result = await db.execute(select(Group).order_by(Group.name))
    groups = result.scalars().all()

    response = []
    for g in groups:
        # Count members
        member_result = await db.execute(
            select(User).where(User.group_id == g.id)
        )
        members = member_result.scalars().all()
        response.append({
            "id": str(g.id),
            "name": g.name,
            "description": g.description,
            "member_count": len(members),
        })

    return {"groups": response, "count": len(response)}


@router.put("/users/{user_id}/group")
async def assign_user_to_group(
    user_id: str,
    group_id: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Assign a user to a group (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if group_id:
        g_result = await db.execute(select(Group).where(Group.id == group_id))
        if g_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Group not found.")

    user.group_id = group_id
    await db.flush()

    return {"message": f"User '{user.username}' assigned to group.", "user_id": str(user.id), "group_id": group_id}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user (admin only). Cannot delete yourself."""
    if str(admin.id) == user_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    await db.delete(user)
    await db.flush()


# --- Ingestion Rules ---


class CreateRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    target_report_name: str = Field(min_length=1, max_length=500)
    subject_contains: str | None = None
    filename_contains: str | None = None
    sender_email: str | None = None
    priority: int = Field(default=10, ge=1, le=100)


class RuleResponse(BaseModel):
    id: str
    name: str
    target_report_name: str
    subject_contains: str | None
    filename_contains: str | None
    sender_email: str | None
    priority: int
    is_active: bool


@router.post("/rules", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_ingestion_rule(
    body: CreateRuleRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> RuleResponse:
    """Create an email ingestion rule (admin only).

    Rules determine which existing report incoming email data gets appended to.
    At least one match condition (subject_contains, filename_contains, sender_email) is required.
    """
    from app.models.ingestion_rule import IngestionRule

    if not body.subject_contains and not body.filename_contains and not body.sender_email:
        raise HTTPException(
            status_code=400,
            detail="At least one match condition is required: subject_contains, filename_contains, or sender_email.",
        )

    rule = IngestionRule(
        name=body.name,
        target_report_name=body.target_report_name,
        subject_contains=body.subject_contains,
        filename_contains=body.filename_contains,
        sender_email=body.sender_email,
        priority=body.priority,
        is_active=True,
        created_by=admin.id,
    )
    db.add(rule)
    await db.flush()

    return RuleResponse(
        id=str(rule.id),
        name=rule.name,
        target_report_name=rule.target_report_name,
        subject_contains=rule.subject_contains,
        filename_contains=rule.filename_contains,
        sender_email=rule.sender_email,
        priority=rule.priority,
        is_active=rule.is_active,
    )


@router.get("/rules")
async def list_ingestion_rules(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all ingestion rules (admin only)."""
    from app.models.ingestion_rule import IngestionRule

    result = await db.execute(
        select(IngestionRule).order_by(IngestionRule.priority.asc())
    )
    rules = result.scalars().all()

    return {
        "rules": [
            {
                "id": str(r.id),
                "name": r.name,
                "target_report_name": r.target_report_name,
                "subject_contains": r.subject_contains,
                "filename_contains": r.filename_contains,
                "sender_email": r.sender_email,
                "priority": r.priority,
                "is_active": r.is_active,
            }
            for r in rules
        ],
        "count": len(rules),
    }


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ingestion_rule(
    rule_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete an ingestion rule (admin only)."""
    from app.models.ingestion_rule import IngestionRule

    result = await db.execute(select(IngestionRule).where(IngestionRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found.")
    await db.delete(rule)
    await db.flush()
