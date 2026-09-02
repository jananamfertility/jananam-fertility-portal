"""
The WhatsApp bot's orchestration: for every inbound message, decides whether
it's a step in the guided booking menu, an opt-in/opt-out command, or a
free-text question to hand to the AI (see ai_bot.py) — then sends the
appropriate reply, updates the contact's funnel stage, and logs everything
to whatsapp_funnel_events for the Marketing tab.

Booking itself reuses the exact same patient-find-or-create + appointment
insert shape as routers.appointments.create_appointment, just with
source="whatsapp".
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import whatsapp_client as wa
from .ai_bot import get_reply
from .config import get_settings

logger = logging.getLogger("bot_flow")


def _clinic_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().clinic_timezone)


def _clinic_now() -> datetime:
    return datetime.now(_clinic_tz())

APPOINTMENT_TYPE_LABELS = {
    "consultation": "Consultation",
    "follow_up": "Follow-up",
    "nt_scan": "NT Scan",
}
DEFAULT_DURATION_MIN = {"consultation": 30, "follow_up": 20, "nt_scan": 45}

OPT_OUT_WORDS = {"stop", "unsubscribe", "opt out", "optout"}
OPT_IN_WORDS = {"yes", "y", "start", "subscribe"}
RESTART_WORDS = {"menu", "restart", "start over", "cancel"}

WELCOME_TEXT = (
    "Hi! 👋 Welcome to Jananam Fertility Centre. I can answer general questions about our "
    "services, or help you book a Consultation, Follow-up, or NT Scan.\n\n"
    "Before we continue: reply YES to allow us to send appointment reminders and occasional "
    "updates here on WhatsApp. You can reply STOP at any time to opt out."
)

_STAGE_ORDER = ["awareness", "interest", "desire", "action", "booked"]


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def log_event(supabase, conversation_id: str, event_type: str, from_stage=None, to_stage=None, metadata=None):
    supabase.table("whatsapp_funnel_events").insert(
        {
            "conversation_id": conversation_id,
            "event_type": event_type,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "metadata": metadata or {},
        }
    ).execute()


def get_or_create_conversation(supabase, phone: str, display_name: str | None) -> dict:
    existing = (
        supabase.table("whatsapp_conversations").select("*").eq("phone", phone).maybe_single().execute()
    )
    if existing.data:
        if display_name and not existing.data.get("display_name"):
            supabase.table("whatsapp_conversations").update({"display_name": display_name}).eq(
                "id", existing.data["id"]
            ).execute()
        return existing.data

    created = (
        supabase.table("whatsapp_conversations")
        .insert({"phone": phone, "display_name": display_name})
        .execute()
    )
    return created.data[0]


def _set_stage(supabase, conversation: dict, new_stage: str) -> dict:
    current = conversation["funnel_stage"]
    if new_stage == current:
        return conversation
    if _STAGE_ORDER.index(new_stage) < _STAGE_ORDER.index(current):
        return conversation  # never regress
    supabase.table("whatsapp_conversations").update(
        {"funnel_stage": new_stage, "last_stage_change_at": _now_iso()}
    ).eq("id", conversation["id"]).execute()
    log_event(supabase, conversation["id"], "stage_change", from_stage=current, to_stage=new_stage)
    conversation["funnel_stage"] = new_stage
    return conversation


def _set_pending(supabase, conversation: dict, pending: dict | None):
    supabase.table("whatsapp_conversations").update({"pending_booking": pending}).eq(
        "id", conversation["id"]
    ).execute()
    conversation["pending_booking"] = pending


def _send_type_menu(phone: str):
    wa.send_button_list(
        phone,
        "Which would you like to book?",
        [
            ("book_type_consultation", "Consultation"),
            ("book_type_follow_up", "Follow-up"),
            ("book_type_nt_scan", "NT Scan"),
        ],
    )


def _send_provider_menu(supabase, phone: str):
    providers = (
        supabase.table("providers")
        .select("id, name, designation")
        .eq("is_active", True)
        .order("name")
        .execute()
        .data
    )
    rows = [("book_provider_any", "No preference", "We'll assign the next available doctor")]
    for p in providers[:9]:
        rows.append((f"book_provider_{p['id']}", p["name"], p.get("designation") or ""))
    wa.send_list_menu(phone, "Who would you like to see?", "Choose doctor", "Doctors", rows)


def _send_date_menu(phone: str):
    today = _clinic_now().date()
    rows = []
    for i in range(1, 8):  # start tomorrow — same-day WhatsApp booking is too tight to confirm reliably
        d = today + timedelta(days=i)
        rows.append((f"book_date_{d.isoformat()}", d.strftime("%a, %d %b"), ""))
    wa.send_list_menu(phone, "Which day works for you?", "Choose date", "Available days", rows)


def _send_time_menu(phone: str):
    morning = [(f"book_time_{h:02d}:00", f"{h}:00 AM" if h != 12 else "12:00 PM", "") for h in [9, 10, 11, 12]]
    afternoon = [
        (f"book_time_{h:02d}:00", f"{h - 12}:00 PM", "") for h in [14, 15, 16, 17, 18]
    ]
    rows = morning + afternoon
    wa.send_list_menu(phone, "What time?", "Choose time", "Available times", rows)


def _find_or_create_patient(supabase, phone: str, full_name: str) -> str:
    existing = supabase.table("patients").select("id").eq("phone", phone).maybe_single().execute()
    if existing.data:
        return existing.data["id"]
    created = supabase.table("patients").insert({"full_name": full_name, "phone": phone}).execute()
    return created.data[0]["id"]


def _complete_booking(supabase, conversation: dict, phone: str, full_name: str, wa_message_id: str):
    pending = conversation["pending_booking"]
    appt_type = pending["type"]
    provider_id = None if pending["provider_id"] == "any" else pending["provider_id"]
    # The date/time menus offer clinic-local wall-clock slots — localize
    # explicitly so this doesn't get stored as if it were UTC.
    naive = datetime.fromisoformat(f"{pending['date']}T{pending['time']}:00")
    starts_at = naive.replace(tzinfo=_clinic_tz())
    ends_at = starts_at + timedelta(minutes=DEFAULT_DURATION_MIN[appt_type])

    patient_id = _find_or_create_patient(supabase, phone, full_name)

    created = (
        supabase.table("appointments")
        .insert(
            {
                "patient_id": patient_id,
                "provider_id": provider_id,
                "appointment_type": appt_type,
                "status": "scheduled",
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat(),
                "source": "whatsapp",
                "whatsapp_message_id": wa_message_id,
            }
        )
        .execute()
    )

    supabase.table("whatsapp_conversations").update(
        {"patient_id": patient_id, "pending_booking": None}
    ).eq("id", conversation["id"]).execute()
    conversation["patient_id"] = patient_id
    _set_stage(supabase, conversation, "booked")
    log_event(
        supabase,
        conversation["id"],
        "booking_completed",
        metadata={"appointment_id": created.data[0]["id"], "appointment_type": appt_type},
    )

    label = APPOINTMENT_TYPE_LABELS[appt_type]
    wa.send_text(
        phone,
        f"You're booked! ✅\n\n{label} on {starts_at.strftime('%A, %d %B')} at "
        f"{starts_at.strftime('%I:%M %p').lstrip('0')}.\n\n"
        "Our front office will confirm shortly. Reply MENU any time to start over.",
    )


def _handle_interactive_reply(supabase, conversation: dict, phone: str, reply_id: str, wa_message_id: str):
    if reply_id.startswith("book_type_"):
        appt_type = reply_id.removeprefix("book_type_")
        _set_pending(supabase, conversation, {"step": "provider", "type": appt_type})
        log_event(supabase, conversation["id"], "booking_started", metadata={"type": appt_type})
        _set_stage(supabase, conversation, "action")
        _send_provider_menu(supabase, phone)
        return

    if reply_id.startswith("book_provider_"):
        provider_id = reply_id.removeprefix("book_provider_")
        pending = {**(conversation.get("pending_booking") or {}), "provider_id": provider_id, "step": "date"}
        _set_pending(supabase, conversation, pending)
        _send_date_menu(phone)
        return

    if reply_id.startswith("book_date_"):
        date_str = reply_id.removeprefix("book_date_")
        pending = {**(conversation.get("pending_booking") or {}), "date": date_str, "step": "time"}
        _set_pending(supabase, conversation, pending)
        _send_time_menu(phone)
        return

    if reply_id.startswith("book_time_"):
        time_str = reply_id.removeprefix("book_time_")
        pending = {**(conversation.get("pending_booking") or {}), "time": time_str, "step": "name"}
        _set_pending(supabase, conversation, pending)
        wa.send_text(phone, "Great — what's the patient's full name?")
        return

    logger.warning("Unrecognized interactive reply id: %s", reply_id)


def handle_inbound_message(
    supabase,
    conversation: dict,
    phone: str,
    message: dict,
    display_name: str | None,
) -> None:
    """Main entry point, called once per inbound WhatsApp message."""
    wa_message_id = message.get("id", "")
    msg_type = message.get("type")

    supabase.table("whatsapp_conversations").update({"last_inbound_at": _now_iso()}).eq(
        "id", conversation["id"]
    ).execute()

    # --- interactive replies (list/button taps) drive the booking menu ---
    if msg_type == "interactive":
        interactive = message.get("interactive", {})
        reply = interactive.get("button_reply") or interactive.get("list_reply")
        if reply:
            _handle_interactive_reply(supabase, conversation, phone, reply["id"], wa_message_id)
        return

    body_text = (message.get("text") or {}).get("body", "").strip()
    if not body_text:
        return
    lowered = body_text.lower().strip()

    # --- opt-in / opt-out commands, checked before anything else ---
    if lowered in OPT_OUT_WORDS:
        supabase.table("whatsapp_conversations").update(
            {"opted_in": False, "opted_out_at": _now_iso()}
        ).eq("id", conversation["id"]).execute()
        log_event(supabase, conversation["id"], "opted_out")
        wa.send_text(phone, "You're unsubscribed from updates. You can still message us here any time.")
        return

    if lowered in OPT_IN_WORDS and not conversation.get("opted_in"):
        supabase.table("whatsapp_conversations").update(
            {"opted_in": True, "opted_in_at": _now_iso()}
        ).eq("id", conversation["id"]).execute()
        log_event(supabase, conversation["id"], "opted_in")
        wa.send_text(
            phone,
            "Thanks! You're all set. Ask me anything about our services, or type MENU to book "
            "an appointment.",
        )
        return

    if lowered in RESTART_WORDS:
        _set_pending(supabase, conversation, None)
        _send_type_menu(phone)
        return

    # --- mid-booking free-text steps (currently just: collecting the name) ---
    pending = conversation.get("pending_booking")
    if pending and pending.get("step") == "name":
        _complete_booking(supabase, conversation, phone, body_text, wa_message_id)
        return

    # --- first-ever message: send the welcome + opt-in prompt, nothing else yet ---
    # (conversation was loaded before this call's last_inbound_at update above, so
    # None here reliably means "this contact has never messaged before".)
    if conversation.get("last_inbound_at") is None:
        wa.send_text(phone, WELCOME_TEXT)
        return

    # --- otherwise: hand off to the AI for a free-text reply + stage judgment ---
    history = (
        supabase.table("whatsapp_messages")
        .select("direction, body")
        .eq("conversation_id", conversation["id"])
        .order("created_at", desc=True)
        .limit(10)
        .execute()
        .data
    )
    history.reverse()
    recent_messages = [
        {"role": "assistant" if m["direction"] == "outbound" else "user", "content": m["body"] or ""}
        for m in history
        if m["body"]
    ]

    result = get_reply(conversation["funnel_stage"], recent_messages, body_text)
    wa.send_text(phone, result["reply"])
    supabase.table("whatsapp_messages").insert(
        {
            "direction": "outbound",
            "from_phone": "",
            "to_phone": phone,
            "body": result["reply"],
            "conversation_id": conversation["id"],
        }
    ).execute()
    supabase.table("whatsapp_conversations").update({"last_outbound_at": _now_iso()}).eq(
        "id", conversation["id"]
    ).execute()

    _set_stage(supabase, conversation, result["suggested_stage"])

    if result["needs_human"]:
        log_event(supabase, conversation["id"], "message_in", metadata={"needs_human": True})
    elif result["should_offer_booking"]:
        _send_type_menu(phone)
