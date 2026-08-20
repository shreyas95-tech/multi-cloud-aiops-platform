"""RBAC middleware for role-based permission enforcement."""

from fastapi import Depends, HTTPException, status

from backend.api.middleware.auth_middleware import get_current_user


def require_role(*allowed_roles: str):
    """Dependency factory that enforces role-based access.

    Creates a FastAPI dependency that checks the authenticated user's role
    against the list of allowed roles for the endpoint.

    Permission mapping:
        - Admin: all endpoints
        - L1_User: KB read endpoints only

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role("Admin"))])
        async def admin_endpoint(): ...

    Args:
        *allowed_roles: One or more role strings that are permitted access.

    Returns:
        A dependency function that validates the user's role.
    """

    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(allowed_roles)}",
            )
        return current_user

    return role_checker


def require_not_first_time():
    """Dependency that blocks first-time users from accessing endpoints.

    First-time users must change their password before accessing any other
    endpoint. Only the password-change endpoint should omit this dependency.

    Usage:
        @router.get("/protected", dependencies=[Depends(require_not_first_time())])
        async def protected_endpoint(): ...

    Returns:
        A dependency function that rejects first-time users with 403.
    """

    async def first_time_checker(current_user: dict = Depends(get_current_user)):
        if current_user.get("first_time", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Password change required before accessing this resource",
            )
        return current_user

    return first_time_checker
