"""
The WhatsApp bot's conversational brain: answers general fertility
questions, keeps the conversation on-topic, and judges which AIDA funnel
stage (awareness / interest / desire / action) the contact is currently in
so the rest of the app can track and later retarget them.

Calls a Claude model through OpenRouter (https://openrouter.ai) — an
OpenAI-compatible API, so this is a plain HTTP call, no extra SDK needed.
When OPENROUTER_API_KEY isn't configured, `get_reply` returns a safe
fallback that nudges the patient toward the guided booking menu instead of
silently failing.
"""
import json
import logging

import httpx

from .config import get_settings

logger = logging.getLogger("ai_bot")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """You are the WhatsApp assistant for Jananam Fertility Centre, a fertility \
clinic. You are talking directly to a prospective or existing patient over WhatsApp.

What you offer at the clinic: Consultation (initial fertility consultation with a doctor), \
Follow-up (for existing patients), and NT Scan (nuchal translucency ultrasound scan). Front-office \
staff handle actual booking through this same chat via a guided menu — your job is the \
conversation before that point.

How to talk:
- Warm, plain-language, and brief (2-4 short sentences per reply, no medical jargon dumps).
- You can explain general fertility concepts (what IVF/IUI/ovulation tracking/common causes of \
difficulty conceiving are, what a first consultation usually involves, what an NT scan checks for) \
in plain terms.
- You must NEVER diagnose, interpret someone's personal symptoms or test results, recommend a \
specific treatment or medication, or give a prognosis. For anything specific to their situation, \
say that's exactly what the doctor covers in a consultation, and offer to help book one.
- Fertility struggles are emotionally sensitive. Never be dismissive, never imply blame, never \
give false reassurance ("I'm sure you'll be fine") — acknowledge feelings briefly and factually \
where relevant, then move the conversation forward.
- If someone describes a medical emergency (heavy bleeding, severe pain, etc.), tell them to \
contact the clinic by phone or go to a hospital immediately — do not continue the sales/booking \
conversation.
- Never invent clinic facts you're not told here (prices, doctor names, specific success rates, \
opening hours). If asked, say a front-office team member can confirm that, or offer to book a \
consultation where it can be discussed.

Funnel stage — classify where this contact is in the AIDA funnel based on the WHOLE conversation, \
not just the latest message. Stages, in order:
- awareness: general/vague learning ("what is IVF", "do you treat PCOS", just browsing)
- interest: asking about the clinic specifically (services, doctors, what's involved, location)
- desire: asking about cost, availability, comparing options, "how do I get started"
- action: explicitly ready to book, asking for an appointment, giving their name/phone to book

Never move the stage backward from where the conversation already was.

Reply with ONLY a JSON object, no other text, in this exact shape:
{"reply": "<the WhatsApp message text to send, plain text, no markdown>", \
"suggested_stage": "awareness|interest|desire|action", \
"should_offer_booking": true|false, \
"needs_human": true|false}

Set should_offer_booking=true when the conversation has reached a natural moment to show the \
booking menu (they've expressed real interest in coming in, or explicitly asked to book). Set \
needs_human=true only for a medical emergency or an explicit request to speak to a person."""

_FALLBACK_REPLY = (
    "Thanks for reaching out to Jananam Fertility Centre! I'm having a little trouble "
    "right now, but I can still help you book a consultation, follow-up, or NT scan — "
    "just let me know which one and I'll take it from there."
)

# Stages only ever move forward through this order.
_STAGE_ORDER = ["awareness", "interest", "desire", "action", "booked"]


def _configured() -> bool:
    return bool(get_settings().openrouter_api_key)


def clamp_forward(current_stage: str, suggested_stage: str) -> str:
    """Never let the AI move a contact's funnel stage backward."""
    try:
        if _STAGE_ORDER.index(suggested_stage) > _STAGE_ORDER.index(current_stage):
            return suggested_stage
    except ValueError:
        pass
    return current_stage


def get_reply(current_stage: str, recent_messages: list[dict], latest_message: str) -> dict:
    """
    recent_messages: list of {"role": "user"|"assistant", "content": str}, oldest first.
    Returns {"reply": str, "suggested_stage": str, "should_offer_booking": bool, "needs_human": bool}.
    """
    if not _configured():
        return {
            "reply": _FALLBACK_REPLY,
            "suggested_stage": current_stage,
            "should_offer_booking": True,
            "needs_human": False,
        }

    settings = get_settings()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.append(
        {"role": "system", "content": f"This contact's current funnel stage is: {current_stage}."}
    )
    messages.extend(recent_messages[-8:])
    messages.append({"role": "user", "content": latest_message})

    try:
        resp = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openrouter_model,
                "messages": messages,
                "temperature": 0.4,
                "max_tokens": 400,
                "response_format": {"type": "json_object"},
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(raw)
        suggested = clamp_forward(current_stage, parsed.get("suggested_stage", current_stage))
        return {
            "reply": str(parsed.get("reply") or _FALLBACK_REPLY)[:1000],
            "suggested_stage": suggested,
            "should_offer_booking": bool(parsed.get("should_offer_booking", False)),
            "needs_human": bool(parsed.get("needs_human", False)),
        }
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
        logger.error("AI bot call failed, falling back: %s", exc)
        return {
            "reply": _FALLBACK_REPLY,
            "suggested_stage": current_stage,
            "should_offer_booking": True,
            "needs_human": False,
        }
