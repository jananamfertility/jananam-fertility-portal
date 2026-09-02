"""Pydantic request/response models. Mirrors supabase/migrations/0001_init.sql."""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .config import get_settings
from .phone_utils import normalize_phone as _normalize_phone


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


class FunnelStage(str, Enum):
    awareness = "awareness"
    interest = "interest"
    desire = "desire"
    action = "action"
    booked = "booked"


class TemplateStatus(str, Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"


class TemplateCategory(str, Enum):
    marketing = "marketing"
    utility = "utility"


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
        # Shared with the WhatsApp bot (see phone_utils.normalize_phone) so
        # a patient entered here and the same person messaging on WhatsApp
        # always resolve to the same row instead of creating a duplicate.
        cleaned = _normalize_phone(v, get_settings().default_country_code)
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


# ---------------------------------------------------------------------------
# WhatsApp bot / AIDA funnel marketing (admin panel)
# ---------------------------------------------------------------------------
class WhatsAppConversationOut(BaseModel):
    id: str
    phone: str
    display_name: Optional[str] = None
    patient_id: Optional[str] = None
    funnel_stage: FunnelStage
    opted_in: bool
    opted_in_at: Optional[datetime] = None
    last_inbound_at: Optional[datetime] = None
    last_outbound_at: Optional[datetime] = None
    created_at: datetime

    # Denormalized so the table doesn't need a second lookup.
    patient: Optional[PatientOut] = None


class FunnelSummary(BaseModel):
    range_start: datetime
    range_end: datetime
    total_contacts: int
    current_by_stage: dict[str, int]        # snapshot: current stage of every contact
    ever_reached_by_stage: dict[str, int]   # funnel: how many contacts ever reached each stage
    # Stage-to-stage conversion, computed from ever_reached_by_stage within this range
    # (e.g. "interest": 0.62 means 62% of contacts who reached awareness also reached
    # interest). This is a range-level ratio, not a strict per-contact cohort trace —
    # a contact who jumped straight from awareness to action is counted at the deepest
    # stage they reached, same as ever_reached_by_stage above.
    conversion_rates: dict[str, float]
    opted_in: int
    opted_in_rate: float
    bookings_from_whatsapp: int
    messages_in_range: int


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    category: TemplateCategory = TemplateCategory.marketing
    body: str = Field(min_length=1, max_length=1024)
    variables: list[str] = Field(default_factory=list)
    target_stage: Optional[FunnelStage] = None


class TemplateUpdate(BaseModel):
    body: Optional[str] = None
    variables: Optional[list[str]] = None
    target_stage: Optional[FunnelStage] = None
    status: Optional[TemplateStatus] = None
    meta_template_name: Optional[str] = None


class TemplateOut(BaseModel):
    id: str
    name: str
    category: TemplateCategory
    body: str
    variables: list[str]
    target_stage: Optional[FunnelStage] = None
    status: TemplateStatus
    meta_template_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RetargetRequest(BaseModel):
    template_id: str
    target_stage: FunnelStage
    inactive_days: int = Field(default=3, ge=0, le=365, description="Only contacts inactive at least this many days")


class RetargetResult(BaseModel):
    matched: int
    sent: int
    skipped_not_opted_in: int
    failed: int
    remaining: int = 0  # matched contacts beyond this call's batch cap — re-run to send them


# ---------------------------------------------------------------------------
# Staff alerts — raised when the AI bot flags an inbound message as needing
# human attention (possible medical emergency, or an explicit request to
# talk to a person), so it's a real, visible item in the admin portal
# instead of only a reply sitting in the chat log.
# ---------------------------------------------------------------------------
class StaffAlertOut(BaseModel):
    id: str
    alert_type: str
    conversation_id: str
    phone: str
    message_excerpt: Optional[str] = None
    created_at: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None


class IntegrationStatus(BaseModel):
    configured: bool
    ok: bool
    detail: str


class IntegrationsHealth(BaseModel):
    whatsapp: IntegrationStatus
    openrouter: IntegrationStatus
