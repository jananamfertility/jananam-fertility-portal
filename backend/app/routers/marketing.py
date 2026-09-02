"""
Admin panel — WhatsApp bot funnel metrics, contact list, retargeting
templates, and sending retargeting campaigns.
"""
import logging
import time
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import ai_bot
from .. import whatsapp_client as wa
from ..auth import StaffUser, get_current_staff, require_admin
from ..bot_flow import log_event
from ..config import get_settings
from ..database import get_supabase
from ..schemas import (
    FunnelSummary,
    IntegrationsHealth,
    RetargetRequest,
    RetargetResult,
    StaffAlertOut,
    TemplateIn,
    TemplateOut,
    TemplateUpdate,
    WhatsAppConversationOut,
)

router = APIRouter(prefix="/api/marketing", tags=["marketing"])
logger = logging.getLogger("marketing")

STAGES = ["awareness", "interest", "desire", "action", "booked"]

# Map Meta's template-review statuses onto our internal TemplateStatus enum.
_META_STATUS_MAP = {
    "APPROVED": "approved",
    "REJECTED": "rejected",
    "PENDING": "submitted",
    "IN_APPEAL": "submitted",
    "PENDING_DELETION": "rejected",
    "PAUSED": "rejected",
    "DISABLED": "rejected",
}

# A retargeting send loop is paced (see send_retargeting_campaign) and capped
# per call to avoid bursting a large number of messages at once, which is
# one of the fastest ways to tank a new WhatsApp number's quality rating.
_RETARGET_BATCH_CAP = 200
_RETARGET_PACE_EVERY = 20
_RETARGET_PACE_SECONDS = 1.0


def _default_month_range() -> tuple[datetime, datetime]:
    now = datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, end


@router.get("/funnel-summary", response_model=FunnelSummary)
def funnel_summary(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    _staff: StaffUser = Depends(get_current_staff),
):
    if start is None or end is None:
        start, end = _default_month_range()

    supabase = get_supabase()

    conversations = supabase.table("whatsapp_conversations").select("funnel_stage, opted_in").execute().data
    total_contacts = len(conversations)
    current_by_stage = Counter(c["funnel_stage"] for c in conversations)
    opted_in = sum(1 for c in conversations if c["opted_in"])

    events = (
        supabase.table("whatsapp_funnel_events")
        .select("to_stage")
        .eq("event_type", "stage_change")
        .gte("created_at", start.isoformat())
        .lt("created_at", end.isoformat())
        .execute()
        .data
    )
    ever_reached_by_stage = Counter(e["to_stage"] for e in events if e["to_stage"])

    # Sequential conversion ratio between adjacent stages, e.g.
    # conversion_rates["interest"] = (contacts who reached interest) /
    # (contacts who reached awareness). See FunnelSummary's docstring for
    # the caveat about this not being a strict per-contact cohort trace.
    conversion_rates: dict[str, float] = {}
    for i in range(1, len(STAGES)):
        prev_stage, this_stage = STAGES[i - 1], STAGES[i]
        prev_count = ever_reached_by_stage.get(prev_stage, 0)
        this_count = ever_reached_by_stage.get(this_stage, 0)
        conversion_rates[this_stage] = round(this_count / prev_count, 4) if prev_count else 0.0

    bookings = (
        supabase.table("appointments")
        .select("id", count="exact")
        .eq("source", "whatsapp")
        .gte("created_at", start.isoformat())
        .lt("created_at", end.isoformat())
        .execute()
    )
    messages = (
        supabase.table("whatsapp_messages")
        .select("id", count="exact")
        .gte("created_at", start.isoformat())
        .lt("created_at", end.isoformat())
        .execute()
    )

    return FunnelSummary(
        range_start=start,
        range_end=end,
        total_contacts=total_contacts,
        current_by_stage={s: current_by_stage.get(s, 0) for s in STAGES},
        ever_reached_by_stage={s: ever_reached_by_stage.get(s, 0) for s in STAGES},
        conversion_rates=conversion_rates,
        opted_in=opted_in,
        opted_in_rate=round(opted_in / total_contacts, 4) if total_contacts else 0.0,
        bookings_from_whatsapp=bookings.count or 0,
        messages_in_range=messages.count or 0,
    )


@router.get("/conversations", response_model=list[WhatsAppConversationOut])
def list_conversations(
    stage: str | None = None,
    opted_in: bool | None = None,
    limit: int = Query(default=100, le=500),
    _staff: StaffUser = Depends(get_current_staff),
):
    supabase = get_supabase()
    query = (
        supabase.table("whatsapp_conversations")
        .select("*, patient:patients(*)")
        .order("last_inbound_at", desc=True)
        .limit(limit)
    )
    if stage:
        query = query.eq("funnel_stage", stage)
    if opted_in is not None:
        query = query.eq("opted_in", opted_in)
    return query.execute().data


@router.get("/alerts", response_model=list[StaffAlertOut])
def list_alerts(
    unacknowledged_only: bool = Query(default=True),
    limit: int = Query(default=50, le=200),
    _staff: StaffUser = Depends(get_current_staff),
):
    supabase = get_supabase()
    query = supabase.table("staff_alerts").select("*").order("created_at", desc=True).limit(limit)
    if unacknowledged_only:
        query = query.is_("acknowledged_at", "null")
    return query.execute().data


@router.post("/alerts/{alert_id}/acknowledge", response_model=StaffAlertOut)
def acknowledge_alert(alert_id: str, staff: StaffUser = Depends(get_current_staff)):
    supabase = get_supabase()
    result = (
        supabase.table("staff_alerts")
        .update({"acknowledged_at": datetime.utcnow().isoformat(), "acknowledged_by": staff.id})
        .eq("id", alert_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found.")
    return result.data[0]


@router.get("/integrations-health", response_model=IntegrationsHealth)
def integrations_health(_staff: StaffUser = Depends(get_current_staff)):
    return IntegrationsHealth(whatsapp=wa.check_health(), openrouter=ai_bot.check_health())


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(_staff: StaffUser = Depends(get_current_staff)):
    supabase = get_supabase()
    return supabase.table("whatsapp_templates").select("*").order("created_at", desc=True).execute().data


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(payload: TemplateIn, staff: StaffUser = Depends(require_admin)):
    supabase = get_supabase()
    row = payload.model_dump()
    row["category"] = row["category"].value if hasattr(row["category"], "value") else row["category"]
    if row.get("target_stage"):
        row["target_stage"] = row["target_stage"].value if hasattr(row["target_stage"], "value") else row["target_stage"]
    row["created_by"] = staff.id
    try:
        created = supabase.table("whatsapp_templates").insert(row).execute()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return created.data[0]


@router.patch("/templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: str, payload: TemplateUpdate, _staff: StaffUser = Depends(require_admin)):
    supabase = get_supabase()
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    for key in ("target_stage", "status"):
        if key in update and update[key] is not None and hasattr(update[key], "value"):
            update[key] = update[key].value
    if not update:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to update.")
    result = supabase.table("whatsapp_templates").update(update).eq("id", template_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
    return result.data[0]


@router.post("/templates/{template_id}/sync-status", response_model=TemplateOut)
def sync_template_status(template_id: str, _staff: StaffUser = Depends(require_admin)):
    """
    Checks the template's real review status with Meta instead of trusting
    the manually-set flag, and updates our record to match. Requires
    WHATSAPP_BUSINESS_ACCOUNT_ID (and a valid access token) to be configured.
    """
    supabase = get_supabase()
    template = supabase.table("whatsapp_templates").select("*").eq("id", template_id).maybe_single().execute()
    if not template.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")

    meta_name = template.data.get("meta_template_name") or template.data["name"]
    meta_status = wa.fetch_template_status(meta_name)
    if meta_status is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Couldn't verify this with Meta yet. Make sure WHATSAPP_BUSINESS_ACCOUNT_ID is set, and "
                f'that a template named "{meta_name}" has been submitted in Meta Business Manager.'
            ),
        )
    mapped_status = _META_STATUS_MAP.get(meta_status, "submitted")
    result = (
        supabase.table("whatsapp_templates")
        .update({"status": mapped_status})
        .eq("id", template_id)
        .execute()
    )
    return result.data[0]


@router.post("/retarget", response_model=RetargetResult)
def send_retargeting_campaign(payload: RetargetRequest, _staff: StaffUser = Depends(require_admin)):
    supabase = get_supabase()
    settings = get_settings()

    template = (
        supabase.table("whatsapp_templates").select("*").eq("id", payload.template_id).maybe_single().execute()
    )
    if not template.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
    if template.data["status"] != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This template hasn't been approved by Meta yet — only approved templates can be sent.",
        )

    meta_template_name = template.data.get("meta_template_name") or template.data["name"]

    # Defense in depth: re-verify against Meta's own record right before
    # sending, rather than trusting our stored "approved" flag alone — a
    # template can be paused, disabled, or re-reviewed after it was first
    # marked approved here.
    if settings.whatsapp_business_account_id:
        live_status = wa.fetch_template_status(meta_template_name)
        if live_status and live_status != "APPROVED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Meta currently reports this template's status as {live_status}, not approved — "
                    "refusing to send. Use \"Sync status\" and try again."
                ),
            )

    cutoff = (datetime.utcnow() - timedelta(days=payload.inactive_days)).isoformat()
    candidates = (
        supabase.table("whatsapp_conversations")
        .select("id, phone, opted_in, last_inbound_at")
        .eq("funnel_stage", payload.target_stage.value)
        .execute()
        .data
    )
    candidates = [c for c in candidates if not c["last_inbound_at"] or c["last_inbound_at"] < cutoff]

    # Cap + pace this batch — sending hundreds of messages in one burst is
    # one of the fastest ways to tank a new WhatsApp number's quality
    # rating. Re-run the campaign to work through any `remaining` contacts.
    remaining = max(0, len(candidates) - _RETARGET_BATCH_CAP)
    batch = candidates[:_RETARGET_BATCH_CAP]

    sent = skipped = failed = 0
    for i, contact in enumerate(batch):
        if not contact["opted_in"]:
            skipped += 1
            continue
        result = wa.send_template(contact["phone"], meta_template_name, "en", [])
        if result is not None:
            sent += 1
            log_event(
                supabase,
                contact["id"],
                "template_sent",
                metadata={"template_id": payload.template_id, "template_name": template.data["name"]},
            )
        else:
            failed += 1

        if (i + 1) % _RETARGET_PACE_EVERY == 0 and (i + 1) < len(batch):
            time.sleep(_RETARGET_PACE_SECONDS)

    return RetargetResult(
        matched=len(candidates), sent=sent, skipped_not_opted_in=skipped, failed=failed, remaining=remaining
    )
