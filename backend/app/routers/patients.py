from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import StaffUser, get_current_staff
from ..database import get_supabase
from ..schemas import PatientIn, PatientOut

router = APIRouter(prefix="/api/patients", tags=["patients"])


@router.get("", response_model=list[PatientOut])
def list_patients(
    search: str | None = Query(default=None, description="Match against name or phone"),
    limit: int = Query(default=25, le=100),
    _staff: StaffUser = Depends(get_current_staff),
):
    supabase = get_supabase()
    query = supabase.table("patients").select("*").order("full_name").limit(limit)
    if search:
        # Supabase/PostgREST OR filter across two columns
        query = query.or_(f"full_name.ilike.%{search}%,phone.ilike.%{search}%")
    result = query.execute()
    return result.data


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: str, _staff: StaffUser = Depends(get_current_staff)):
    supabase = get_supabase()
    result = supabase.table("patients").select("*").eq("id", patient_id).maybe_single().execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return result.data


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def create_patient(payload: PatientIn, _staff: StaffUser = Depends(get_current_staff)):
    supabase = get_supabase()
    existing = (
        supabase.table("patients").select("*").eq("phone", payload.phone).maybe_single().execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A patient with this phone number already exists ({existing.data['full_name']}).",
        )
    result = supabase.table("patients").insert(payload.model_dump()).execute()
    return result.data[0]


@router.patch("/{patient_id}", response_model=PatientOut)
def update_patient(
    patient_id: str, payload: PatientIn, _staff: StaffUser = Depends(get_current_staff)
):
    supabase = get_supabase()
    result = (
        supabase.table("patients")
        .update(payload.model_dump())
        .eq("id", patient_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return result.data[0]
