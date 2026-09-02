-- Jananam Fertility Centre — fixes for the WhatsApp bot gap audit
-- (see KNOWN_GAPS.md). Adds: a staff_alerts table for real, visible
-- emergency/needs-human alerts; per-contact AI rate-limit tracking columns
-- on whatsapp_conversations; and a one-time backfill that normalizes
-- existing patients.phone values to the same canonical shape the app now
-- writes everywhere (see backend/app/phone_utils.py), so already-registered
-- patients start matching a WhatsApp contact on the same number.

-- ============================================================================
-- STAFF ALERTS
-- Raised when the AI bot flags an inbound message as needing human
-- attention (possible medical emergency, or an explicit request to talk to
-- a person) — see backend/app/bot_flow.py::_raise_staff_alert.
-- ============================================================================
create table if not exists public.staff_alerts (
  id                 uuid primary key default gen_random_uuid(),
  alert_type         text not null default 'needs_human',
  conversation_id    uuid not null references public.whatsapp_conversations(id) on delete cascade,
  phone              text not null,
  message_excerpt    text,
  created_at         timestamptz not null default now(),
  acknowledged_at    timestamptz,
  acknowledged_by    uuid references public.staff_profiles(id)
);

create index if not exists staff_alerts_unacknowledged_idx
  on public.staff_alerts (created_at desc) where acknowledged_at is null;
create index if not exists staff_alerts_conversation_idx on public.staff_alerts (conversation_id);

comment on table public.staff_alerts is
  'Real, visible alerts for messages the AI bot flagged as needing human attention — not just a log entry.';

alter table public.staff_alerts enable row level security;

drop policy if exists staff_alerts_all on public.staff_alerts;
create policy staff_alerts_all on public.staff_alerts
  for all using (public.is_active_staff()) with check (public.is_active_staff());

-- ============================================================================
-- PER-CONTACT AI RATE LIMIT
-- Sliding window tracked directly on the conversation row — see
-- backend/app/bot_flow.py::_check_ai_rate_limit.
-- ============================================================================
alter table public.whatsapp_conversations
  add column if not exists ai_call_window_started_at timestamptz,
  add column if not exists ai_call_count int not null default 0;

-- ============================================================================
-- BACKFILL: normalize existing patient phone numbers
-- Digits only, country-code-prefixed, no "+" — the same shape WhatsApp's
-- webhook sends inbound numbers in. Skips (and reports via NOTICE) any row
-- whose normalized number would collide with another existing patient —
-- those need a manual look before merging, since merging patient identities
-- also means reassigning their appointments/whatsapp_conversations, which
-- this migration deliberately does not do automatically.
-- ============================================================================
do $$
declare
  r record;
  digits text;
  normalized text;
  skipped_count int := 0;
begin
  for r in select id, phone from public.patients loop
    digits := regexp_replace(coalesce(r.phone, ''), '[^0-9]', '', 'g');
    if digits = '' then
      continue;
    end if;

    if length(digits) = 11 and left(digits, 1) = '0' then
      digits := substring(digits from 2);
    end if;

    if length(digits) = 10 then
      normalized := '91' || digits;  -- DEFAULT_COUNTRY_CODE — matches backend/app/config.py
    else
      normalized := digits;
    end if;

    if normalized <> r.phone then
      begin
        update public.patients set phone = normalized, updated_at = now() where id = r.id;
      exception when unique_violation then
        skipped_count := skipped_count + 1;
        raise notice 'Skipped patient % (phone "%") — normalized value "%" already belongs to another patient. Needs a manual merge.',
          r.id, r.phone, normalized;
      end;
    end if;
  end loop;

  if skipped_count > 0 then
    raise notice '% patient(s) skipped during phone normalization — see NOTICEs above for details.', skipped_count;
  end if;
end $$;
