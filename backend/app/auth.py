"""
Authentication for the booking portal.

The frontend signs users in directly against Supabase Auth (email +
password) and sends the resulting access token to this API as
`Authorization: Bearer <token>` on every request. This module verifies
that token and loads the caller's staff profile, so every route handler
gets a trusted `StaffUser` instead of ever seeing a raw token.
"""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .config import get_settings
from .database import get_supabase

_bearer = HTTPBearer(auto_error=False)


class StaffUser(BaseModel):
    id: str
    email: str | None = None
    full_name: str
    role: str
    is_active: bool


def _decode_token(token: str) -> dict:
    settings = get_settings()
    if not settings.supabase_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_JWT_SECRET is not configured on the server.",
        )
    try:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired session ({exc}). Please log in again.",
        ) from exc


async def get_current_staff(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> StaffUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
        )

    claims = _decode_token(credentials.credentials)
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    supabase = get_supabase()
    result = (
        supabase.table("staff_profiles")
        .select("id, full_name, role, is_active")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    profile = result.data
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This account is not set up as a front-office user yet. "
                "Ask an admin to add a staff_profiles row for it."
            ),
        )
    if not profile["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    return StaffUser(
        id=profile["id"],
        email=claims.get("email"),
        full_name=profile["full_name"],
        role=profile["role"],
        is_active=profile["is_active"],
    )


def require_admin(staff: StaffUser = Depends(get_current_staff)) -> StaffUser:
    if staff.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires an admin account.",
        )
    return staff
