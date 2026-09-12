-- Jananam Fertility Centre — source-context personalization + lighter menu
-- cadence (see KNOWN_GAPS.md, "2026-09-12 review" section). Both columns
-- were applied directly against the live project earlier in that session
-- (via the Supabase MCP) without a matching migration file being checked
-- in at the time -- this file catches the repo's migration history up to
-- match what's actually live, so a fresh/staging database built from
-- migrations alone doesn't come up missing these columns.

-- ============================================================================
-- SOURCE CONTEXT
-- The contact's very first inbound message (often the website's WhatsApp
-- button pre-fill, which now varies by page) -- see
-- backend/app/bot_flow.py::_welcome_text_for and ai_bot.py::get_reply's
-- source_context param.
-- ============================================================================
alter table public.whatsapp_conversations
  add column if not exists source_context text;

-- ============================================================================
-- MENU REMINDER CADENCE
-- Counts plain conversational AI replies since the tappable main menu was
-- last shown, so it resurfaces every Nth reply instead of after literally
-- every one -- see backend/app/bot_flow.py::_MENU_REMINDER_EVERY.
-- ============================================================================
alter table public.whatsapp_conversations
  add column if not exists messages_since_menu integer not null default 0;
