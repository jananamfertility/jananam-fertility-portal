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

GRAPH_API_VERSION = "v20.0"


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
