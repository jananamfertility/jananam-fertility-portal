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

    # Phase 2 — WhatsApp Cloud API webhook
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
