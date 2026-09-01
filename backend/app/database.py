"""
Supabase client, shared across the app.

We talk to Supabase with the *service role* key from the backend only
(never exposed to the frontend). That key bypasses Row Level Security, so
`app.auth` is what stands in for RLS on the API side: every route depends
on `get_current_staff`, which verifies the caller's Supabase Auth JWT and
confirms they are an active row in `staff_profiles` before any query runs.

RLS is still enabled on every table (see supabase/migrations/0001_init.sql)
as defense-in-depth, in case a table is ever queried directly (e.g. a future
mobile app using the anon key) rather than through this API.
"""
from functools import lru_cache

from supabase import create_client, Client

from .config import get_settings


@lru_cache
def get_supabase() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not configured. "
            "Copy backend/.env.example to backend/.env and fill in your "
            "Supabase project's values."
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
