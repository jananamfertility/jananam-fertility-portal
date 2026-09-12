"""
The WhatsApp bot's orchestration: for every inbound message, decides whether
it's a step in the guided booking menu, an opt-in/opt-out command, a request
to view/cancel/reschedule an existing appointment, or a free-text question
to hand to the AI (see ai_bot.py) — then sends the appropriate reply,
updates the contact's funnel stage, and logs everything to
whatsapp_funnel_events for the Marketing tab.

Booking itself reuses the exact same patient-find-or-create + appointment
insert shape as routers.appointments.create_appointment, just with
source="whatsapp", and runs every booking/reschedule through the same
provider-overlap check the portal API uses (see scheduling.has_overlap) so
neither path can double-book a provider.
"""
import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import alerting
from . import whatsapp_client as wa
from .ai_bot import get_reply
from .config import get_settings
from .scheduling import has_overlap

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
MY_APPOINTMENTS_WORDS = {
    "my appointments", "my appointment", "appointments", "my bookings",
    "my booking", "view appointments", "upcoming appointments",
}
_CONFIRM_WORDS = {"yes", "y", "yeah", "yep", "correct", "that's me", "thats me", "right"}
# A plain greeting from a returning, already-opted-in contact would otherwise
# fall straight through to the AI (see handle_inbound_message) and get a
# conversational reply with no tappable menu at all -- most people open with
# "Hi", not the literal word "menu", so treat these the same as RESTART_WORDS.
GREETING_WORDS = {
    "hi", "hii", "hiii", "hello", "helo", "hey", "heya", "hiya", "yo", "hai",
    "good morning", "good afternoon", "good evening", "gm",
}
# Words that indicate the person's own message is actually asking to book,
# not just asking about the clinic in general -- see _has_explicit_booking_intent.
_BOOKING_INTENT_SUBSTRINGS = ("book", "appointment", "schedule")


def _has_explicit_booking_intent(lowered_text: str) -> bool:
    return any(kw in lowered_text for kw in _BOOKING_INTENT_SUBSTRINGS)


WELCOME_TEXT = (
    "Hi! 👋 I'm Asha, Jananam Fertility Centre's AI care assistant. I'm here to answer your "
    "questions and help you book a Consultation, Follow-up, or NT Scan — whatever's easiest for "
    "you.\n\n"
    "Before we continue: reply YES to allow us to send appointment reminders and occasional "
    "updates here on WhatsApp. You can reply STOP at any time to opt out."
)

# The website's click-to-chat button pre-fills a message that now varies by
# page -- e.g. "Hi, I'd like to know more about Egg Freezing" -- so the very
# first message a contact ever sends is a useful hint about what brought them
# in. Used only to personalize the welcome text's opening line (falls back to
# the generic WELCOME_TEXT when it doesn't match) and is also stored as-is on
# the conversation as source_context, to softly steer the AI's later replies
# (see ai_bot.get_reply's source_context param).
_SOURCE_TOPIC_RE = re.compile(r"know more about\s+(.+)", re.IGNORECASE)


def _extract_topic(source_text: str | None) -> str | None:
    if not source_text:
        return None
    match = _SOURCE_TOPIC_RE.search(source_text)
    if not match:
        return None
    topic = match.group(1).strip().strip(".!?").strip()
    if not topic or len(topic) > 60:
        return None
    return topic


def _welcome_text_for(source_text: str | None) -> str:
    topic = _extract_topic(source_text)
    if not topic:
        return WELCOME_TEXT
    return (
        f"Hi! 👋 I'm Asha, Jananam Fertility Centre's AI care assistant. I saw you're interested "
        f"in {topic} — happy to help with any questions, or book a Consultation, Follow-up, or "
        "NT Scan whenever you're ready.\n\n"
        "Before we continue: reply YES to allow us to send appointment reminders and occasional "
        "updates here on WhatsApp. You can reply STOP at any time to opt out."
    )

# Static, staff-reviewed copy for the top-of-funnel main menu taps — deliberately
# NOT AI-generated, so what a prospective patient reads about treatments, the
# clinic, and costs is accurate and consistent every time, with no model-call
# latency/cost or hallucination risk. Facts sourced from jananamfertility.com;
# review these if the site's claims ever change.
_TREATMENTS_INFO_TEXT = (
    "We offer a full range of fertility treatments: IVF, IUI, ICSI/PICSI, donor egg IVF, "
    "fertility preservation (egg, embryo, and sperm freezing), and NT scans — all through our "
    "own on-site, ART-certified embryology lab.\n\n"
    "Every treatment plan is personalised after a proper evaluation with the doctor — there's "
    "no one-size-fits-all approach here.\n\n"
    "Reply MENU to see more, or ask me anything about a specific treatment."
)
_ABOUT_CLINIC_INFO_TEXT = (
    "Jananam Fertility Centre has been serving patients in Neelankarai, Chennai since 2013, led "
    "by Dr. Vani Sundarapandian (MD, DGO, MRCOG-UK), who brings 25+ years of experience in "
    "reproductive medicine.\n\n"
    "We're a single-specialty fertility clinic — this is the only thing we focus on, not one "
    "department among many.\n\n"
    "Reply MENU to see more, or ask me anything."
)
_COSTS_INFO_TEXT = (
    "We believe in transparency: your treatment plan and its costs are discussed clearly with "
    "you before anything begins, with no hidden charges or surprise add-ons.\n\n"
    "A first consultation lets the doctor understand your situation and give you an accurate, "
    "personalised cost estimate — every case is different, so we don't quote prices blind over "
    "WhatsApp.\n\n"
    "Reply MENU to see more, or BOOK to schedule a consultation."
)

_STAGE_ORDER = ["awareness", "interest", "desire", "action", "booked"]

# Free-text messages longer than this are truncated before being sent to the
# AI model — keeps a single message from ballooning cost, and bounds how
# much text a prompt-injection attempt can stuff into one turn. The full
# message is still stored in whatsapp_messages either way.
_AI_MESSAGE_CHAR_LIMIT = 1500


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
    # NOTE: maybe_single() returns None outright (not a response object with
    # .data = None) when zero rows match, on the supabase-py version this
    # project pins — so `existing` itself, not just `.data`, needs the guard.
    existing = (
        supabase.table("whatsapp_conversations").select("*").eq("phone", phone).maybe_single().execute()
    )
    if existing and existing.data:
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


def _send_main_menu(phone: str):
    """
    Top-of-funnel menu shown right after opt-in and whenever someone types
    MENU — gives Awareness/Interest/Desire-stage contacts something to tap
    besides "book now", instead of assuming everyone who messages is
    already ready to book (see _send_type_menu for that Action-stage menu).
    """
    wa.send_list_menu(
        phone,
        "How can I help you today?",
        "Menu",
        "Jananam Fertility Centre",
        [
            ("menu_learn_treatments", "Learn about treatments", "IVF, IUI, fertility scans & more"),
            ("menu_about_clinic", "About our clinic", "Our doctor, experience & approach"),
            ("menu_cost_expect", "Costs & what to expect", "Transparent pricing, first visit info"),
            ("menu_book", "Book an appointment", "Consultation, follow-up or NT scan"),
            ("menu_my_appts", "My appointments", "View, reschedule or cancel"),
            ("menu_talk_human", "Talk to our team", "Connect with front office"),
        ],
    )


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


def _existing_patient_name(supabase, phone: str) -> str | None:
    existing = supabase.table("patients").select("full_name").eq("phone", phone).maybe_single().execute()
    return existing.data["full_name"] if existing and existing.data else None


def _find_or_create_patient(supabase, phone: str, full_name: str) -> str:
    existing = supabase.table("patients").select("id").eq("phone", phone).maybe_single().execute()
    if existing and existing.data:
        return existing.data["id"]
    created = supabase.table("patients").insert({"full_name": full_name, "phone": phone}).execute()
    return created.data[0]["id"]


def _send_my_appointments_menu(supabase, conversation: dict, phone: str):
    patient_id = conversation.get("patient_id")
    if not patient_id:
        existing = supabase.table("patients").select("id").eq("phone", phone).maybe_single().execute()
        patient_id = existing.data["id"] if existing and existing.data else None
    if not patient_id:
        wa.send_text(phone, "I don't see any appointments booked under this number yet. Type MENU to book one.")
        return

    now_utc_iso = datetime.now(ZoneInfo("UTC")).isoformat()
    rows_data = (
        supabase.table("appointments")
        .select("id, appointment_type, starts_at")
        .eq("patient_id", patient_id)
        .in_("status", ["scheduled", "confirmed"])
        .gte("starts_at", now_utc_iso)
        .order("starts_at")
        .limit(8)
        .execute()
        .data
    )
    if not rows_data:
        wa.send_text(phone, "You don't have any upcoming appointments booked. Type MENU to book one.")
        return

    rows = []
    for r in rows_data:
        starts = datetime.fromisoformat(r["starts_at"]).astimezone(_clinic_tz())
        label = APPOINTMENT_TYPE_LABELS.get(r["appointment_type"], r["appointment_type"])
        when = starts.strftime("%a %d %b, %I:%M %p").replace(" 0", " ")
        rows.append((f"appt_{r['id']}", when, label))
    wa.send_list_menu(
        phone,
        "Here are your upcoming appointments — tap one to cancel or reschedule it.",
        "View",
        "Your appointments",
        rows,
    )


def _attempt_booking(supabase, conversation: dict, phone: str, given_name: str, wa_message_id: str, family_mismatch: bool):
    pending = conversation["pending_booking"]
    appt_type = pending["type"]
    provider_id = None if pending["provider_id"] == "any" else pending["provider_id"]
    naive = datetime.fromisoformat(f"{pending['date']}T{pending['time']}:00")
    starts_at = naive.replace(tzinfo=_clinic_tz())
    ends_at = starts_at + timedelta(minutes=DEFAULT_DURATION_MIN[appt_type])

    if provider_id and has_overlap(supabase, provider_id, starts_at.isoformat(), ends_at.isoformat()):
        # Slot got taken between the menu being shown and the name being
        # collected — keep everything else we already know and only ask
        # for a new time, instead of restarting the whole flow.
        retry_pending = {**pending, "step": "time", "name": given_name, "family_mismatch": family_mismatch}
        _set_pending(supabase, conversation, retry_pending)
        wa.send_text(phone, "Sorry — that slot was just taken. Please pick another time:")
        _send_time_menu(phone)
        return

    patient_id = _find_or_create_patient(supabase, phone, given_name)

    notes = None
    if family_mismatch:
        notes = (
            f'Booked via WhatsApp for "{given_name}" — this phone number\'s patient record is under a '
            "different name. Please verify who this appointment is actually for before confirming."
        )

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
                "notes": notes,
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
        metadata={
            "appointment_id": created.data[0]["id"],
            "appointment_type": appt_type,
            "family_mismatch": family_mismatch,
        },
    )

    label = APPOINTMENT_TYPE_LABELS[appt_type]
    confirm = (
        f"You're booked! ✅\n\n{label} on {starts_at.strftime('%A, %d %B')} at "
        f"{starts_at.strftime('%I:%M %p').lstrip('0')}.\n\n"
    )
    if family_mismatch:
        confirm += "Our front office will confirm the patient's details with you shortly. "
    else:
        confirm += "Our front office will confirm shortly. "
    confirm += "Reply MENU any time to start over, or MY APPOINTMENTS to see your bookings."
    wa.send_text(phone, confirm)


def _attempt_reschedule(supabase, conversation: dict, phone: str):
    pending = conversation["pending_booking"]
    appt_id = pending["reschedule_appointment_id"]
    appt_type = pending["type"]
    provider_id = None if pending["provider_id"] == "any" else pending["provider_id"]
    naive = datetime.fromisoformat(f"{pending['date']}T{pending['time']}:00")
    starts_at = naive.replace(tzinfo=_clinic_tz())
    ends_at = starts_at + timedelta(minutes=DEFAULT_DURATION_MIN[appt_type])

    if provider_id and has_overlap(
        supabase, provider_id, starts_at.isoformat(), ends_at.isoformat(), exclude_appointment_id=appt_id
    ):
        _set_pending(supabase, conversation, {**pending, "step": "time"})
        wa.send_text(phone, "Sorry — that slot was just taken. Please pick another time:")
        _send_time_menu(phone)
        return

    supabase.table("appointments").update(
        {"starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat(), "status": "scheduled"}
    ).eq("id", appt_id).execute()
    _set_pending(supabase, conversation, None)
    log_event(supabase, conversation["id"], "message_in", metadata={"rescheduled_appointment_id": appt_id})

    label = APPOINTMENT_TYPE_LABELS[appt_type]
    wa.send_text(
        phone,
        f"Done — your {label} is now on {starts_at.strftime('%A, %d %B')} at "
        f"{starts_at.strftime('%I:%M %p').lstrip('0')}. Reply MENU any time.",
    )


def _handle_interactive_reply(supabase, conversation: dict, phone: str, reply_id: str, wa_message_id: str):
    # --- main menu taps (see _send_main_menu) — each maps to one AIDA stage ---
    if reply_id == "menu_learn_treatments":
        _set_stage(supabase, conversation, "awareness")
        log_event(supabase, conversation["id"], "message_in", metadata={"menu_tap": "learn_treatments"})
        wa.send_text(phone, _TREATMENTS_INFO_TEXT)
        return

    if reply_id == "menu_about_clinic":
        _set_stage(supabase, conversation, "interest")
        log_event(supabase, conversation["id"], "message_in", metadata={"menu_tap": "about_clinic"})
        wa.send_text(phone, _ABOUT_CLINIC_INFO_TEXT)
        return

    if reply_id == "menu_cost_expect":
        _set_stage(supabase, conversation, "desire")
        log_event(supabase, conversation["id"], "message_in", metadata={"menu_tap": "cost_expect"})
        wa.send_text(phone, _COSTS_INFO_TEXT)
        return

    if reply_id == "menu_book":
        _set_stage(supabase, conversation, "action")
        log_event(supabase, conversation["id"], "message_in", metadata={"menu_tap": "book"})
        _send_type_menu(phone)
        return

    if reply_id == "menu_my_appts":
        _send_my_appointments_menu(supabase, conversation, phone)
        return

    if reply_id == "menu_talk_human":
        log_event(supabase, conversation["id"], "message_in", metadata={"menu_tap": "talk_human"})
        wa.send_text(
            phone,
            "Sure — I've let our front office know you'd like to speak with someone. They'll reach "
            "out here on WhatsApp or call you shortly. Reply MENU any time in the meantime.",
        )
        _raise_staff_alert(supabase, conversation, phone, "Contact tapped 'Talk to our team' from the main menu.")
        return

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
        pending = {**(conversation.get("pending_booking") or {}), "time": time_str}

        if pending.get("reschedule_appointment_id"):
            _set_pending(supabase, conversation, pending)
            _attempt_reschedule(supabase, conversation, phone)
            return

        if pending.get("name"):
            # Retry after a slot-conflict bounce — we already have the name
            # (and any family-mismatch flag) from before, skip re-asking.
            _set_pending(supabase, conversation, pending)
            _attempt_booking(
                supabase, conversation, phone, pending["name"], wa_message_id, pending.get("family_mismatch", False)
            )
            return

        existing_name = _existing_patient_name(supabase, phone)
        if existing_name:
            pending["step"] = "confirm_name"
            pending["candidate_name"] = existing_name
            _set_pending(supabase, conversation, pending)
            wa.send_text(
                phone,
                f"Is this appointment for {existing_name}? Reply YES, or send the patient's full name if "
                "it's for someone else.",
            )
        else:
            pending["step"] = "name"
            _set_pending(supabase, conversation, pending)
            wa.send_text(phone, "Great — what's the patient's full name?")
        return

    if reply_id.startswith("appt_"):
        appt_id = reply_id.removeprefix("appt_")
        wa.send_button_list(
            phone,
            "What would you like to do with this appointment?",
            [
                (f"apptcancel_{appt_id}", "Cancel"),
                (f"apptreschedule_{appt_id}", "Reschedule"),
                (f"apptkeep_{appt_id}", "Never mind"),
            ],
        )
        return

    if reply_id.startswith("apptcancel_"):
        appt_id = reply_id.removeprefix("apptcancel_")
        supabase.table("appointments").update({"status": "cancelled"}).eq("id", appt_id).execute()
        log_event(supabase, conversation["id"], "message_in", metadata={"cancelled_appointment_id": appt_id})
        wa.send_text(phone, "Done — that appointment has been cancelled. Type MENU any time to book another.")
        return

    if reply_id.startswith("apptreschedule_"):
        appt_id = reply_id.removeprefix("apptreschedule_")
        appt = (
            supabase.table("appointments")
            .select("id, appointment_type, provider_id")
            .eq("id", appt_id)
            .maybe_single()
            .execute()
        )
        if not appt or not appt.data:
            wa.send_text(phone, "Sorry, I couldn't find that appointment anymore.")
            return
        pending = {
            "step": "date",
            "type": appt.data["appointment_type"],
            "provider_id": appt.data["provider_id"] or "any",
            "reschedule_appointment_id": appt_id,
        }
        _set_pending(supabase, conversation, pending)
        wa.send_text(phone, "Sure — let's pick a new day and time.")
        _send_date_menu(phone)
        return

    if reply_id.startswith("apptkeep_"):
        wa.send_text(phone, "No changes made. Type MENU any time.")
        return

    logger.warning("Unrecognized interactive reply id: %s", reply_id)


def _check_ai_rate_limit(supabase, conversation: dict) -> bool:
    """
    Bounds OpenRouter spend/abuse per contact: at most
    settings.ai_max_calls_per_window free-text AI replies per
    ai_rate_window_hours, per phone number. Returns True if this call is
    allowed (and records it); False if the contact is over the limit.
    """
    settings = get_settings()
    now = datetime.now(ZoneInfo("UTC"))
    window_started_raw = conversation.get("ai_call_window_started_at")
    count = conversation.get("ai_call_count") or 0

    window_started = None
    if window_started_raw:
        try:
            window_started = datetime.fromisoformat(window_started_raw)
        except ValueError:
            window_started = None

    if not window_started or (now - window_started) > timedelta(hours=settings.ai_rate_window_hours):
        window_started = now
        count = 0

    if count >= settings.ai_max_calls_per_window:
        return False

    supabase.table("whatsapp_conversations").update(
        {"ai_call_window_started_at": window_started.isoformat(), "ai_call_count": count + 1}
    ).eq("id", conversation["id"]).execute()
    conversation["ai_call_window_started_at"] = window_started.isoformat()
    conversation["ai_call_count"] = count + 1
    return True


def _raise_staff_alert(supabase, conversation: dict, phone: str, excerpt: str):
    try:
        supabase.table("staff_alerts").insert(
            {
                "alert_type": "needs_human",
                "conversation_id": conversation["id"],
                "phone": phone,
                "message_excerpt": excerpt[:500],
            }
        ).execute()
    except Exception:
        logger.exception("Failed to record staff_alerts row for conversation %s", conversation["id"])
    alerting.send_emergency_email(phone, excerpt[:500])


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
        wa.send_text(phone, "Thanks! You're all set.")
        _send_main_menu(phone)
        return

    if lowered in RESTART_WORDS:
        _set_pending(supabase, conversation, None)
        _send_main_menu(phone)
        return

    if lowered in MY_APPOINTMENTS_WORDS:
        _send_my_appointments_menu(supabase, conversation, phone)
        return

    # --- mid-booking free-text steps ---
    pending = conversation.get("pending_booking")
    if pending and pending.get("step") == "confirm_name":
        candidate = pending.get("candidate_name", "")
        if lowered in _CONFIRM_WORDS:
            _attempt_booking(supabase, conversation, phone, candidate, wa_message_id, family_mismatch=False)
        else:
            _attempt_booking(supabase, conversation, phone, body_text, wa_message_id, family_mismatch=True)
        return
    if pending and pending.get("step") == "name":
        _attempt_booking(supabase, conversation, phone, body_text, wa_message_id, family_mismatch=False)
        return

    # --- first-ever message: send the welcome + opt-in prompt, nothing else yet ---
    # (conversation was loaded before this call's last_inbound_at update above, so
    # None here reliably means "this contact has never messaged before".)
    if conversation.get("last_inbound_at") is None:
        source_context = body_text[:500]
        supabase.table("whatsapp_conversations").update({"source_context": source_context}).eq(
            "id", conversation["id"]
        ).execute()
        conversation["source_context"] = source_context
        wa.send_text(phone, _welcome_text_for(body_text))
        return

    # --- plain greetings get the tappable main menu directly, not AI chatter ---
    if lowered in GREETING_WORDS:
        _send_main_menu(phone)
        return

    # --- otherwise: hand off to the AI for a free-text reply + stage judgment ---
    if not _check_ai_rate_limit(supabase, conversation):
        log_event(supabase, conversation["id"], "message_in", metadata={"ai_rate_limited": True})
        wa.send_text(
            phone,
            "You've sent quite a few messages recently, so let's use the quick menu instead — type MENU to "
            "book an appointment, or call the clinic directly for anything urgent.",
        )
        return

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
        {"role": "assistant" if m["direction"] == "outbound" else "user", "content": (m["body"] or "")[:800]}
        for m in history
        if m["body"]
    ]

    result = get_reply(
        conversation["funnel_stage"],
        recent_messages,
        body_text[:_AI_MESSAGE_CHAR_LIMIT],
        conversation.get("source_context"),
    )
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
        _raise_staff_alert(supabase, conversation, phone, body_text)
        # Still show the menu after an emergency/human-request flag -- the
        # AI's own reply already tells them to call/go to hospital for a true
        # emergency, this just leaves something tappable either way.
        _send_main_menu(phone)
    elif result["should_offer_booking"] and _has_explicit_booking_intent(lowered):
        # The AI thought this was a good moment AND the person's own message
        # actually asked to book -- skip the main menu and jump straight to
        # picking a booking type. should_offer_booking alone was too eager:
        # plain curiosity like "what is ivf" or "what are your charges" was
        # tripping it and skipping the main menu every time.
        _send_type_menu(phone)
    else:
        # Whatever they typed, they should always end up with a tappable
        # menu, not just a wall of AI text with nothing to do next.
        _send_main_menu(phone)
