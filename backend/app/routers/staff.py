"""
Admin panel — staff accounts.

Front-office logins are Supabase Auth users. Rather than sending admins to
the Supabase dashboard to create one, this router uses the Supabase Admin
API (available because the backend holds the service role key) to create
the auth user directly; the `handle_new_user` trigger then creates the
matching `staff_profiles` row automatically.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import StaffUser, get_current_staff, require_admin
from ..database import get_supabase
from ..schemas import StaffCreate, StaffOut, StaffUpdate

router = APIRouter(prefix="/api/staff", tags=["staff"])


@router.get("", response_model=list[StaffOut])
def list_staff(_staff: StaffUser = Depends(require_admin)):
    supabase = get_supabase()
    result = (
        supabase.table("staff_profiles")
        .select("id, email, full_name, role, is_active, created_at")
        .order("full_name")
        .execute()
    )
    return result.data


@router.post("", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
def create_staff(payload: StaffCreate, staff: StaffUser = Depends(require_admin)):
    supabase = get_supabase()
    try:
        created = supabase.auth.admin.create_user(
            {
                "email": payload.email,
                "password": payload.password,
                "email_confirm": True,
                "user_metadata": {"full_name": payload.full_name},
            }
        )
    except Exception as exc:  # supabase-py raises its own AuthApiError etc.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not create the account: {exc}",
        ) from exc

    new_id = created.user.id

    # The trigger inserts with role='front_office' by default — patch it if
    # the admin asked for something else.
    if payload.role.value != "front_office":
        supabase.table("staff_profiles").update({"role": payload.role.value}).eq(
            "id", new_id
        ).execute()

    result = (
        supabase.table("staff_profiles")
        .select("id, email, full_name, role, is_active, created_at")
        .eq("id", new_id)
        .single()
        .execute()
    )
    return result.data


@router.patch("/{staff_id}", response_model=StaffOut)
def update_staff(
    staff_id: str, payload: StaffUpdate, staff: StaffUser = Depends(require_admin)
):
    if staff_id == staff.id and (payload.is_active is False or payload.role == "front_office"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can't deactivate or demote your own account. Ask another admin to do it.",
        )

    supabase = get_supabase()
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if "role" in update and update["role"] is not None:
        update["role"] = update["role"].value if hasattr(update["role"], "value") else update["role"]

    if not update:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to update.")

    result = supabase.table("staff_profiles").update(update).eq("id", staff_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found.")
    return result.data[0]
