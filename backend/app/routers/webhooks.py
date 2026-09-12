"""
Phase 2 — WhatsApp Cloud API webhook. Live: inbound messages are answered
by the guided booking menu / AI bot in `app.bot_flow`, and bookings made
here land in the same `appointments` table the portal reads, with
source="whatsapp".
"""
import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from .. import whatsapp_client as wa
from ..bot_flow import get_or_create_conversation, handle_inbound_message
from ..config import get_settings
from ..database import get_supabase
from ..phone_utils import normalize_phone

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
        # Not configured yet — reject rather than silently trusting
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

            # Delivery/read status updates for messages we sent — just log,
            # nothing to act on yet.
            for wa_status in value.get("statuses", []):
                logger.info("WhatsApp status update: %s", wa_status)

            contacts = value.get("contacts", [])
            profile_name = None
            if contacts:
                profile_name = (contacts[0].get("profile") or {}).get("name")

            for message in value.get("messages", []):
                # WhatsApp already sends "from" in the canonical
                # digits-with-country-code shape, but normalize it through
                # the same function the portal uses anyway — cheap
                # insurance against Meta ever changing that, and it keeps
                # this the single source of truth for "what does a phone
                # number look like once it's in our database".
                from_phone = normalize_phone(message.get("from", ""), settings.default_country_code)
                to_phone = value.get("metadata", {}).get("display_phone_number", "")
                wa_message_id = message.get("id")
                body_text = (message.get("text") or {}).get("body")

                # Mark read + show "typing..." as early as possible, on its own
                # so a hiccup here never blocks actually handling the message
                # -- this is what makes the reply that follows (often a few
                # seconds away, waiting on the AI call) feel like someone's
                # actually there instead of dead air.
                try:
                    wa.mark_read_with_typing(wa_message_id)
                except Exception:
                    logger.exception("Failed to mark message %s as read / show typing indicator", wa_message_id)

                try:
                    conversation = get_or_create_conversation(supabase, from_phone, profile_name)

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
                            "to_phone": to_phone,
                            "body": body_text,
                            "raw_payload": message,
                            "patient_id": patient.data["id"] if patient and patient.data else None,
                            "conversation_id": conversation["id"],
                        }
                    ).execute()

                    handle_inbound_message(supabase, conversation, from_phone, message, profile_name)
                    logger.info("Handled inbound WhatsApp message %s from %s", wa_message_id, from_phone)
                except Exception:
                    # A bug in the bot must never take down the webhook (Meta
                    # disables webhooks that error repeatedly) — the message
                    # is already logged above either way.
                    logger.exception(
                        "Error handling inbound WhatsApp message %s from %s", wa_message_id, from_phone
                    )

    return {"status": "received"}
