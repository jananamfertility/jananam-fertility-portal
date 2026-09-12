"""
Sends WhatsApp appointment reminders. Meant to run as a scheduled job (the
"jananam-fertility-reminders" Render Cron Job) roughly hourly.

Finds appointments starting in about REMINDER_LEAD_HOURS from now that
haven't been reminded yet, and sends each opted-in patient a reminder via
an approved WhatsApp message template -- reminders go out well outside the
24-hour free-form messaging window, so Meta requires a pre-approved
template rather than a plain text message (see KNOWN_GAPS.md, "No
appointment reminders" for the background, and 0006_appointment_reminders.sql
for the template row this script looks up).

Safe to run repeatedly / on overlapping schedules: reminder_sent_at is set
on the appointment the moment a send is attempted, so a given appointment
is only ever reminded once, even if this runs more often than appointments
actually need reminding.

Run from the backend/ directory so the `app` package import below resolves
the same way the main service's own code does:
    cd backend && python scripts/send_reminders.py
"""
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import whatsapp_client as wa  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import get_supabase  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("send_reminders")

APPOINTMENT_TYPE_LABELS = {
    "consultation": "Consultation",
    "follow_up": "Follow-up",
    "nt_scan": "NT Scan",
}

# How far ahead of an appointment to remind, and how wide a window to check
# each run. The window is wider than the cron interval (hourly) so a
# slightly delayed run, or an overlap between runs, never skips an
# appointment that falls between two checks.
REMINDER_LEAD_HOURS = 24
REMINDER_WINDOW_HOURS = 2

# Must match the meta_template_name in the whatsapp_templates row created by
# 0006_appointment_reminders.sql, and the template name actually submitted
# in Meta Business Manager.
REMINDER_TEMPLATE_META_NAME = "appointment_reminder_24h"
REMINDER_TEMPLATE_LANGUAGE = "en"


def main() -> None:
    supabase = get_supabase()
    settings = get_settings()

    if not settings.whatsapp_business_account_id:
        logger.warning(
            "WHATSAPP_BUSINESS_ACCOUNT_ID isn't set -- can't verify the reminder template's approval "
            "status with Meta, so refusing to send anything this run (safer than sending an unverified "
            "template)."
        )
        return

    # Refuse to send anything until Meta has actually approved this template
    # -- better to silently skip a run than fail loudly per-message (a send
    # attempt against an unapproved/rejected template just errors anyway).
    live_status = wa.fetch_template_status(REMINDER_TEMPLATE_META_NAME)
    if live_status != "APPROVED":
        logger.warning(
            "Reminder template %r is not APPROVED yet (Meta status: %s) -- skipping this run entirely. "
            "Submit it in Meta Business Manager and wait for approval; see KNOWN_GAPS.md.",
            REMINDER_TEMPLATE_META_NAME,
            live_status,
        )
        return

    clinic_tz = ZoneInfo(settings.clinic_timezone)
    now_utc = datetime.now(ZoneInfo("UTC"))
    window_start = now_utc + timedelta(hours=REMINDER_LEAD_HOURS)
    window_end = window_start + timedelta(hours=REMINDER_WINDOW_HOURS)

    appointments = (
        supabase.table("appointments")
        .select("id, patient_id, appointment_type, starts_at")
        .in_("status", ["scheduled", "confirmed"])
        .is_("reminder_sent_at", "null")
        .gte("starts_at", window_start.isoformat())
        .lt("starts_at", window_end.isoformat())
        .execute()
        .data
    )
    if not appointments:
        logger.info("No appointments need a reminder this run (window %s to %s).", window_start, window_end)
        return

    sent = skipped_no_patient = skipped_not_opted_in = failed = 0

    for appt in appointments:
        patient = (
            supabase.table("patients")
            .select("full_name, phone")
            .eq("id", appt["patient_id"])
            .maybe_single()
            .execute()
        )
        if not patient or not patient.data:
            skipped_no_patient += 1
            continue
        phone = patient.data["phone"]

        conversation = (
            supabase.table("whatsapp_conversations")
            .select("opted_in")
            .eq("phone", phone)
            .maybe_single()
            .execute()
        )
        if not conversation or not conversation.data or not conversation.data.get("opted_in"):
            # The opt-in prompt specifically asks permission to send
            # "appointment reminders" -- respect a decline/opt-out the same
            # way retargeting does, rather than treating reminders as exempt.
            skipped_not_opted_in += 1
            continue

        first_name = (patient.data.get("full_name") or "there").split()[0]
        label = APPOINTMENT_TYPE_LABELS.get(appt["appointment_type"], appt["appointment_type"])
        starts = datetime.fromisoformat(appt["starts_at"]).astimezone(clinic_tz)
        date_str = starts.strftime("%A, %d %B")
        time_str = starts.strftime("%I:%M %p").lstrip("0")

        result = wa.send_template(
            phone,
            REMINDER_TEMPLATE_META_NAME,
            REMINDER_TEMPLATE_LANGUAGE,
            [first_name, label, date_str, time_str],
        )

        # Mark as attempted either way -- a hard send failure (bad number,
        # etc.) shouldn't be retried forever on every future run; a genuine
        # transient failure is rare enough to handle manually if it ever
        # comes up, rather than risk double-sending on a blind retry.
        supabase.table("appointments").update(
            {"reminder_sent_at": datetime.utcnow().isoformat()}
        ).eq("id", appt["id"]).execute()

        if result is not None:
            sent += 1
        else:
            failed += 1

    logger.info(
        "Reminder run complete: sent=%d failed=%d skipped_no_patient=%d skipped_not_opted_in=%d",
        sent,
        failed,
        skipped_no_patient,
        skipped_not_opted_in,
    )


if __name__ == "__main__":
    main()
