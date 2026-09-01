"""Pydantic request/response models. Mirrors supabase/migrations/0001_init.sql."""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class AppointmentType(str, Enum):
    consultation = "consultation"
    follow_up = "follow_up"
    nt_scan = "nt_scan"


class AppointmentStatus(str, Enum):
    scheduled = "scheduled"
    confirmed = "confirmed"
    completed = "completed"
    no_show = "no_show"
    cancelled = "cancelled"


class AppointmentSource(str, Enum):
    manual = "manual"
    whatsapp = "whatsapp"


class StaffRole(str, Enum):
    front_office = "front_office"
    admin = "admin"


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
class ProviderIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    designation: Optional[str] = None
    is_active: bool = True


class ProviderOut(ProviderIn):
    id: str


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------
class PatientIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=6, max_length=20)
    age: Optional[int] = Field(default=None, ge=0, le=120)
    partner_name: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        cleaned = "".join(ch for ch in v if ch.isdigit() or ch == "+")
        if len(cleaned) < 6:
            raise ValueError("Phone number looks too short.")
        return cleaned


class PatientOut(PatientIn):
    id: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------
class AppointmentCreate(BaseModel):
    # Either reference an existing patient...
    patient_id: Optional[str] = None
    # ...or supply their details inline and the API will find-or-create them
    # by phone number.
    patient: Optional[PatientIn] = None

    provider_id: Optional[str] = None
    appointment_type: AppointmentType
    status: AppointmentStatus = AppointmentStatus.scheduled

    starts_at: datetime
    ends_at: datetime

    notes: Optional[str] = None

    @field_validator("ends_at")
    @classmethod
    def ends_after_start(cls, v: datetime, info):
        starts_at = info.data.get("starts_at")
        if starts_at and v <= starts_at:
            raise ValueError("ends_at must be after starts_at.")
        return v


class AppointmentUpdate(BaseModel):
    """All fields optional — only what's supplied gets patched."""

    patient_id: Optional[str] = None
    patient: Optional[PatientIn] = None
    provider_id: Optional[str] = None
    appointment_type: Optional[AppointmentType] = None
    status: Optional[AppointmentStatus] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    notes: Optional[str] = None


class AppointmentOut(BaseModel):
    id: str
    patient_id: str
    provider_id: Optional[str] = None
    appointment_type: AppointmentType
    status: AppointmentStatus
    starts_at: datetime
    ends_at: datetime
    notes: Optional[str] = None
    source: AppointmentSource
    whatsapp_message_id: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Denormalized for the calendar UI so it doesn't need N+1 lookups.
    patient: Optional[PatientOut] = None
    provider: Optional[ProviderOut] = None


# ---------------------------------------------------------------------------
# Staff (admin panel)
# ---------------------------------------------------------------------------
class StaffOut(BaseModel):
    id: str
    email: Optional[str] = None
    full_name: str
    role: StaffRole
    is_active: bool
    created_at: datetime


class StaffCreate(BaseModel):
    email: str = Field(min_length=3)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, description="Temporary password — the user can change it after logging in.")
    role: StaffRole = StaffRole.front_office


class StaffUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[StaffRole] = None
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Reports (admin panel)
# ---------------------------------------------------------------------------
class ReportSummary(BaseModel):
    range_start: datetime
    range_end: datetime
    total: int
    kept: int  # total minus cancelled — what actually happened or is on the books
    by_type: dict[str, int]
    by_status: dict[str, int]
    by_weekday: dict[str, int]  # "Mon".."Sun" -> count (cancelled excluded)
    by_provider: dict[str, int]  # provider name -> count (cancelled excluded)
    no_show_rate: float  # no_show / kept
    cancellation_rate: float  # cancelled / total
