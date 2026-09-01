"""
Phase 2 — WhatsApp Cloud API webhook.

This is intentionally built and wired in NOW, even though the clinic is
starting with manual booking only, so switching on WhatsApp later is a
config change (env vars + turning on auto-booking logic) rather than a
re-architecture. Today it:

  1. Answers Meta's webhook verification handshake (GET).
  2. Accepts inbound message/status payloads (POST), verifies the request
     really came from Meta using the app secret, and logs every event into
     `whatsapp_messages` — matching to an existing patient by phone number
     when there is one.

What it deliberately does NOT do yet: parse free-text messages into a
booking, or send messages back. That's the phase-2 build-out — see the
TODO block below for exactly where that logic plugs in.
"""
import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from ..config import get_settings
from ..database import get_supabase

router = APIRouter(prefix="/api/webhooks/whatsapp", tags=["webhooks"])
logger = logging.getLogger("whatsapp_webhook")


@router.get("")
def verify_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    """
    Meta calls this once, when you register the webhook URL in the Meta App
    Dashboard, to confirm you control this endpoint.
    """
    settings = get_settings()
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return int(hub_challenge)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification failed.")


def _verify_signature(body: bytes, signature_header: str | None, app_secret: str) -> bool:
    if not app_secret:
        # Phase 2 not configured yet — reject rather than silently trusting
        # unauthenticated input once this endpoint is public.
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


@router.post("", status_code=status.HTTP_200_OK)
async def receive_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
):
    settings = get_settings()
    raw_body = await request.body()

    if not _verify_signature(raw_body, x_hub_signature_256, settings.whatsapp_app_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad signature.")

    payload = await request.json()
    supabase = get_supabase()

    # WhatsApp Cloud API payload shape:
    # entry[].changes[].value.messages[] / .statuses[]
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            for message in value.get("messages", []):
                from_phone = message.get("from", "")
                body_text = (message.get("text") or {}).get("body")
                wa_message_id = message.get("id")

                patient = (
                    supabase.table("patients")
                    .select("id")
                    .eq("phone", from_phone)
                    .maybe_single()
                    .execute()
                )

                supabase.table("whatsapp_messages").insert(
                    {
                        "wa_message_id": wa_message_id,
                        "direction": "inbound",
                        "from_phone": from_phone,
                        "to_phone": value.get("metadata", {}).get("display_phone_number", ""),
                        "body": body_text,
                        "raw_payload": message,
                        "patient_id": patient.data["id"] if patient.data else None,
                    }
                ).execute()

                # ------------------------------------------------------------------
                # TODO (phase 2 activation): turn logged messages into bookings.
                #
                #   1. If `patient.data` is None, this is a new patient — either
                #      create a `patients` row from their WhatsApp profile name
                #      (value["contacts"][0]["profile"]["name"]) or reply asking
                #      for their name.
                #   2. Parse `body_text` (or drive a structured reply-button /
                #      list-message flow) to get appointment type + preferred
                #      date/time.
                #   3. Reuse `AppointmentCreate` + the same logic as
                #      `routers.appointments.create_appointment`, but with
                #      source="whatsapp" and whatsapp_message_id=wa_message_id.
                #   4. Send a confirmation back via the Cloud API's /messages
                #      endpoint (needs a permanent access token + phone_number_id,
                #      add WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID to
                #      config.py when this is built).
                # ------------------------------------------------------------------
                logger.info("Logged inbound WhatsApp message %s from %s", wa_message_id, from_phone)

    return {"status": "received"}
