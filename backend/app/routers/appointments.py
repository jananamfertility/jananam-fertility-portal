from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import StaffUser, get_current_staff
from ..database import get_supabase
from ..scheduling import has_overlap
from ..schemas import (
    AppointmentCreate,
    AppointmentOut,
    AppointmentStatus,
    AppointmentUpdate,
)

router = APIRouter(prefix="/api/appointments", tags=["appointments"])

# Pull the appointment row plus its patient/provider in one round trip so the
# calendar view never has to do N+1 lookups.
_SELECT = "*, patient:patients(*), provider:providers(*)"


def _find_or_create_patient(supabase, patient_id: str | None, patient_in) -> str:
    if patient_id:
        found = (
            supabase.table("patients").select("id").eq("id", patient_id).maybe_single().execute()
        )
        if not found or not found.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
        return patient_id

    if not patient_in:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either patient_id or patient details.",
        )

    existing = (
        supabase.table("patients")
        .select("id")
        .eq("phone", patient_in.phone)
        .maybe_single()
        .execute()
    )
    if existing and existing.data:
        return existing.data["id"]

    created = supabase.table("patients").insert(patient_in.model_dump()).execute()
    return created.data[0]["id"]


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    start: datetime | None = Query(default=None, description="Range start (inclusive)"),
    end: datetime | None = Query(default=None, description="Range end (exclusive)"),
    provider_id: str | None = None,
    status_filter: AppointmentStatus | None = Query(default=None, alias="status"),
    _staff: StaffUser = Depends(get_current_staff),
):
    supabase = get_supabase()
    query = supabase.table("appointments").select(_SELECT).order("starts_at")
    if start:
        query = query.gte("starts_at", start.isoformat())
    if end:
        query = query.lt("starts_at", end.isoformat())
    if provider_id:
        query = query.eq("provider_id", provider_id)
    if status_filter:
        query = query.eq("status", status_filter.value)
    return query.execute().data


@router.get("/{appointment_id}", response_model=AppointmentOut)
def get_appointment(appointment_id: str, _staff: StaffUser = Depends(get_current_staff)):
    supabase = get_supabase()
    result = (
        supabase.table("appointments")
        .select(_SELECT)
        .eq("id", appointment_id)
        .maybe_single()
        .execute()
    )
    if not result or not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found.")
    return result.data


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(payload: AppointmentCreate, staff: StaffUser = Depends(get_current_staff)):
    supabase = get_supabase()
    patient_id = _find_or_create_patient(supabase, payload.patient_id, payload.patient)

    if payload.provider_id and payload.status != AppointmentStatus.cancelled and has_overlap(
        supabase, payload.provider_id, payload.starts_at.isoformat(), payload.ends_at.isoformat()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This provider already has an appointment during that time.",
        )

    row = {
        "patient_id": patient_id,
        "provider_id": payload.provider_id,
        "appointment_type": payload.appointment_type.value,
        "status": payload.status.value,
        "starts_at": payload.starts_at.isoformat(),
        "ends_at": payload.ends_at.isoformat(),
        "notes": payload.notes,
        "source": "manual",
        "created_by": staff.id,
        "updated_by": staff.id,
    }
    created = supabase.table("appointments").insert(row).execute()
    new_id = created.data[0]["id"]
    return (
        supabase.table("appointments").select(_SELECT).eq("id", new_id).single().execute().data
    )


@router.patch("/{appointment_id}", response_model=AppointmentOut)
def update_appointment(
    appointment_id: str,
    payload: AppointmentUpdate,
    staff: StaffUser = Depends(get_current_staff),
):
    supabase = get_supabase()
    existing = (
        supabase.table("appointments")
        .select("id, starts_at, ends_at, provider_id, status")
        .eq("id", appointment_id)
        .maybe_single()
        .execute()
    )
    if not existing or not existing.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found.")

    update: dict = {"updated_by": staff.id}

    if payload.patient_id or payload.patient:
        update["patient_id"] = _find_or_create_patient(supabase, payload.patient_id, payload.patient)
    if payload.provider_id is not None:
        update["provider_id"] = payload.provider_id
    if payload.appointment_type is not None:
        update["appointment_type"] = payload.appointment_type.value
    if payload.status is not None:
        update["status"] = payload.status.value
    if payload.starts_at is not None:
        update["starts_at"] = payload.starts_at.isoformat()
    if payload.ends_at is not None:
        update["ends_at"] = payload.ends_at.isoformat()
    if payload.notes is not None:
        update["notes"] = payload.notes

    starts_at = payload.starts_at or datetime.fromisoformat(existing.data["starts_at"])
    ends_at = payload.ends_at or datetime.fromisoformat(existing.data["ends_at"])
    if ends_at <= starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ends_at must be after starts_at.",
        )

    final_provider_id = update.get("provider_id", existing.data["provider_id"])
    final_status = update.get("status", existing.data["status"])
    if (
        final_provider_id
        and final_status != AppointmentStatus.cancelled.value
        and has_overlap(
            supabase,
            final_provider_id,
            starts_at.isoformat(),
            ends_at.isoformat(),
            exclude_appointment_id=appointment_id,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This provider already has an appointment during that time.",
        )

    supabase.table("appointments").update(update).eq("id", appointment_id).execute()
    return (
        supabase.table("appointments")
        .select(_SELECT)
        .eq("id", appointment_id)
        .single()
        .execute()
        .data
    )


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment(appointment_id: str, _staff: StaffUser = Depends(get_current_staff)):
    supabase = get_supabase()
    result = supabase.table("appointments").delete().eq("id", appointment_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found.")
    return None
