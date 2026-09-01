from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import StaffUser, get_current_staff, require_admin
from ..database import get_supabase
from ..schemas import ProviderIn, ProviderOut

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("", response_model=list[ProviderOut])
def list_providers(
    include_inactive: bool = False, _staff: StaffUser = Depends(get_current_staff)
):
    supabase = get_supabase()
    query = supabase.table("providers").select("*").order("name")
    if not include_inactive:
        query = query.eq("is_active", True)
    return query.execute().data


@router.post("", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
def create_provider(payload: ProviderIn, _staff: StaffUser = Depends(require_admin)):
    supabase = get_supabase()
    result = supabase.table("providers").insert(payload.model_dump()).execute()
    return result.data[0]


@router.patch("/{provider_id}", response_model=ProviderOut)
def update_provider(
    provider_id: str, payload: ProviderIn, _staff: StaffUser = Depends(require_admin)
):
    supabase = get_supabase()
    result = (
        supabase.table("providers").update(payload.model_dump()).eq("id", provider_id).execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found.")
    return result.data[0]
