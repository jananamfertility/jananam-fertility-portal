"""
Thin wrapper around the WhatsApp Cloud API (Meta Graph API) for sending
messages. Every function is a no-op (logs and returns None) when
WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID aren't configured yet, so
the webhook can be deployed and tested (receiving + logging + the AI/booking
logic) before those credentials exist.
"""
import logging

import httpx

from .config import get_settings

logger = logging.getLogger("whatsapp_client")

GRAPH_API_VERSION = "v26.0"


def _configured() -> bool:
    settings = get_settings()
    return bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id)


def _base_url() -> str:
    settings = get_settings()
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{settings.whatsapp_phone_number_id}/messages"


def _headers() -> dict:
    settings = get_settings()
    return {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }


def _post(payload: dict) -> dict | None:
    if not _configured():
        logger.info(
            "WhatsApp not configured (WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID "
            "missing) — skipping send. Payload would have been: %s",
            payload,
        )
        return None
    try:
        resp = httpx.post(_base_url(), headers=_headers(), json=payload, timeout=15.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        logger.error("WhatsApp send failed: %s", exc)
        return None


def send_text(to_phone: str, body: str) -> dict | None:
    return _post(
        {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": body, "preview_url": False},
        }
    )


def mark_read_with_typing(wa_message_id: str) -> dict | None:
    """
    Marks an inbound message as read (blue ticks on the patient's side) and
    shows a "typing..." indicator at the same time -- the Cloud API's own
    combined mechanism for this, not a custom effect. The indicator clears
    itself after ~25 seconds or as soon as we actually send a reply,
    whichever comes first, so this should be called as early as possible
    when a message comes in, before the (often few-second) AI call.
    """
    if not wa_message_id:
        return None
    return _post(
        {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": wa_message_id,
            "typing_indicator": {"type": "text"},
        }
    )


def send_button_list(to_phone: str, body: str, buttons: list[tuple[str, str]]) -> dict | None:
    """buttons: list of (id, title) — WhatsApp allows at most 3 reply buttons."""
    return _post(
        {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": bid, "title": title[:20]}}
                        for bid, title in buttons[:3]
                    ]
                },
            },
        }
    )


def send_list_menu(
    to_phone: str, body: str, button_label: str, section_title: str, rows: list[tuple[str, str, str]]
) -> dict | None:
    """rows: list of (id, title, description) — WhatsApp allows up to 10 rows."""
    return _post(
        {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body},
                "action": {
                    "button": button_label[:20],
                    "sections": [
                        {
                            "title": section_title[:24],
                            "rows": [
                                {"id": rid, "title": title[:24], "description": desc[:72]}
                                for rid, title, desc in rows[:10]
                            ],
                        }
                    ],
                },
            },
        }
    )


def check_health() -> dict:
    """Lightweight reachability check for the admin portal's integrations panel."""
    settings = get_settings()
    if not _configured():
        return {
            "configured": False,
            "ok": False,
            "detail": "WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID are not set.",
        }
    try:
        resp = httpx.get(
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/{settings.whatsapp_phone_number_id}",
            params={"fields": "id"},
            headers=_headers(),
            timeout=8.0,
        )
        if resp.status_code == 200:
            return {"configured": True, "ok": True, "detail": "Connected."}
        return {
            "configured": True,
            "ok": False,
            "detail": f"Graph API returned HTTP {resp.status_code} — the access token may have expired.",
        }
    except httpx.HTTPError as exc:
        return {"configured": True, "ok": False, "detail": f"Request to the Graph API failed: {exc}"}


def fetch_template_status(template_name: str) -> str | None:
    """
    Looks up a template's real approval status from Meta (APPROVED / PENDING
    / REJECTED / IN_APPEAL / PAUSED / DISABLED), so the admin portal doesn't
    have to trust a manually-set flag. Returns None if this can't be
    determined yet (business account ID not configured, or no matching
    template found) rather than guessing.
    """
    settings = get_settings()
    if not settings.whatsapp_access_token or not settings.whatsapp_business_account_id:
        return None
    try:
        resp = httpx.get(
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/{settings.whatsapp_business_account_id}/message_templates",
            params={"name": template_name},
            headers=_headers(),
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return None
        return data[0].get("status")
    except httpx.HTTPError as exc:
        logger.error("Template status check for %r failed: %s", template_name, exc)
        return None


def send_template(to_phone: str, template_name: str, language_code: str, variables: list[str]) -> dict | None:
    """
    Sends a pre-approved Meta template message (the only kind allowed
    outside the 24-hour customer-service window — i.e. retargeting).
    `variables` fill the template's {{1}}, {{2}}... placeholders in order.
    """
    components = []
    if variables:
        components.append(
            {
                "type": "body",
                "parameters": [{"type": "text", "text": v} for v in variables],
            }
        )
    return _post(
        {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components,
            },
        }
    )
