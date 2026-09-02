"""
Authentication for the booking portal.

The frontend signs users in directly against Supabase Auth (email +
password) and sends the resulting access token to this API as
`Authorization: Bearer <token>` on every request. This module verifies
that token and loads the caller's staff profile, so every route handler
gets a trusted `StaffUser` instead of ever seeing a raw token.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .database import get_supabase

_bearer = HTTPBearer(auto_error=False)


class StaffUser(BaseModel):
    id: str
    email: str | None = None
    full_name: str
    role: str
    is_active: bool


async def get_current_staff(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> StaffUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
        )

    supabase = get_supabase()

    # Verify the access token against Supabase Auth itself, rather than
    # decoding it locally. This works no matter which signing scheme the
    # project uses (legacy shared HS256 secret, or the newer asymmetric
    # JWT signing keys) and never falls out of sync with a rotated secret.
    try:
        user_resp = supabase.auth.get_user(credentials.credentials)
    except Exception as exc:  # supabase-py raises on invalid/expired tokens
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired session ({exc}). Please log in again.",
        ) from exc

    user = user_resp.user if user_resp else None
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please log in again.",
        )

    result = (
        supabase.table("staff_profiles")
        .select("id, full_name, role, is_active")
        .eq("id", user.id)
        .maybe_single()
        .execute()
    )
    profile = result.data if result else None
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
        email=user.email,
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
