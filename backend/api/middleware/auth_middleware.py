"""Authentication middleware for JWT validation and token blacklist checking."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.database import get_db
from backend.security import decode_access_token

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> dict:
    """FastAPI dependency that validates the JWT Bearer token.

    Extracts the token from the Authorization header, decodes it,
    checks the jti against the token blacklist, and returns the user claims.

    Returns:
        A dict with keys: username, role, first_time, jti

    Raises:
        HTTPException 401: If token is missing, invalid, expired, or blacklisted.
    """
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jti = payload.get("jti")
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing jti",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check token blacklist
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT 1 FROM token_blacklist WHERE jti = ?", (jti,)
        )
        if await cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return {
        "username": payload.get("sub"),
        "role": payload.get("role"),
        "first_time": payload.get("first_time", False),
        "jti": jti,
    }
