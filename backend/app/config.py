"""
Centralized settings, loaded from environment variables / .env.

Nothing in here should be hardcoded per-clinic — this file is the single
place that reads configuration so deployment (dev, staging, phase-2 with
WhatsApp turned on) never requires touching application code.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # CORS
    cors_origins: str = "http://localhost:5173"

    # IANA timezone the clinic operates in — used to interpret the day/time
    # a patient picks in the WhatsApp booking menu as clinic-local wall-clock
    # time (rather than accidentally storing it as UTC).
    clinic_timezone: str = "Asia/Kolkata"

    # Phase 2 — WhatsApp Cloud API webhook
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    # Permanent access token + phone number ID from the Meta App dashboard —
    # required to *send* messages (replies, booking menus, template/
    # retargeting sends). Without these the webhook still receives and logs
    # messages, it just can't reply.
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    # WhatsApp Business Account ID — only needed for template management
    # (listing/creating message templates via the Graph API). Retargeting
    # sends work fine without it as long as templates are created once in
    # the Meta Business Manager UI.
    whatsapp_business_account_id: str = ""
    # The clinic's public WhatsApp number, in international format with no
    # symbols (e.g. "919812345678") — used to build the wa.me click-to-chat
    # link for the website widget. Usually the same number as above.
    whatsapp_public_number: str = ""

    # AI bot — conversational replies + fertility knowledge + funnel-stage
    # judgment, via OpenRouter (https://openrouter.ai), calling a Claude
    # model. Without a key, the bot falls back to the guided menu only (no
    # free-text understanding).
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-sonnet-4.5"

    # Per-contact AI usage cap — bounds OpenRouter spend/abuse from any one
    # WhatsApp number. Once a contact hits ai_max_calls_per_window free-text
    # AI replies inside ai_rate_window_hours, the bot falls back to the
    # guided menu instead of calling the AI again until the window rolls over.
    ai_max_calls_per_window: int = 20
    ai_rate_window_hours: int = 24

    # Default country code (digits only, no +) used to interpret a bare
    # 10-digit phone number typed into the portal, so it normalizes to the
    # same E.164-without-plus shape WhatsApp's webhook sends inbound numbers
    # in (e.g. "9812345678" -> "919812345678"). Change this if the clinic is
    # not in India.
    default_country_code: str = "91"

    # Optional: real out-of-band email alert when the AI bot flags a message
    # as needing human attention (possible medical emergency, or an explicit
    # request to speak to a person). Without these, the alert still shows in
    # the admin portal, it just won't also email anyone.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    staff_alert_email_to: str = ""

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
