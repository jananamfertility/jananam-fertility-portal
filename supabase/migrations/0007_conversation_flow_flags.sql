-- Jananam Fertility Centre — fixes two conversation bugs reported after
-- real testing (see KNOWN_GAPS.md):
--
-- 1. Any not-yet-opted-in contact who ever typed a bare "yes" (answering
--    ANY question at all, not just the opt-in prompt) had it silently
--    reinterpreted as "yes, opt me in" -- derailing the conversation into
--    "Thanks! You're all set." + the main menu, even when they were
--    actually saying yes to something else entirely (e.g. "want to book a
--    consultation?"). awaiting_opt_in_reply scopes that literal-YES
--    interception to exactly one message: the contact's very next reply
--    after the welcome/opt-in prompt is sent, and only that one.
--
-- 2. When Asha's own reply wove in a gentle consultation invitation
--    ("I can help you book one whenever you're ready") but the contact's
--    own wording didn't contain an explicit booking word ("book",
--    "appointment", "schedule"), a plain "yes" in response just got
--    treated as ordinary chat and the person was left looking at a
--    generic menu instead of moving toward booking. ai_offered_booking
--    remembers that Asha's last reply made that invitation, so a short
--    affirmative reply on the very next turn is read as accepting it and
--    jumps straight to the booking-type menu. Also a one-shot flag -- it
--    only ever governs the single very next inbound message.
--
-- See backend/app/bot_flow.py::handle_inbound_message for both.

alter table public.whatsapp_conversations
  add column if not exists awaiting_opt_in_reply boolean not null default false;

alter table public.whatsapp_conversations
  add column if not exists ai_offered_booking boolean not null default false;
