-- Jananam Fertility Centre — WhatsApp bot + AIDA funnel tracking
-- Adds: one row per WhatsApp contact (whatsapp_conversations), a funnel
-- event log for analytics/conversion tracking (whatsapp_funnel_events),
-- and a table for retargeting message templates (whatsapp_templates).
-- whatsapp_messages (from 0001) is extended with a conversation_id link.

-- ============================================================================
-- ENUMS
-- ============================================================================
do $$ begin
  create type funnel_stage as enum ('awareness', 'interest', 'desire', 'action', 'booked');
exception when duplicate_object then null; end $$;

do $$ begin
  create type template_status as enum ('draft', 'submitted', 'approved', 'rejected');
exception when duplicate_object then null; end $$;

do $$ begin
  create type funnel_event_type as enum (
    'message_in', 'message_out', 'stage_change', 'opted_in', 'opted_out',
    'booking_started', 'booking_completed', 'template_sent'
  );
exception when duplicate_object then null; end $$;

-- ============================================================================
-- WHATSAPP CONVERSATIONS
-- One row per phone number that has ever messaged the bot. This is the
-- "contact" record the Marketing tab and retargeting sends work off of.
-- ============================================================================
create table if not exists public.whatsapp_conversations (
  id                  uuid primary key default gen_random_uuid(),
  phone               text not null unique,
  display_name        text,
  patient_id          uuid references public.patients(id) on delete set null,

  funnel_stage        funnel_stage not null default 'awareness',
  pending_booking      jsonb,   -- in-progress guided-menu booking state, if any

  opted_in            boolean not null default false,
  opted_in_at         timestamptz,
  opted_out_at        timestamptz,

  last_inbound_at     timestamptz,
  last_outbound_at    timestamptz,
  last_stage_change_at timestamptz,

  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

create index if not exists whatsapp_conversations_phone_idx on public.whatsapp_conversations (phone);
create index if not exists whatsapp_conversations_stage_idx on public.whatsapp_conversations (funnel_stage);
create index if not exists whatsapp_conversations_patient_idx on public.whatsapp_conversations (patient_id);

comment on table public.whatsapp_conversations is
  'One row per WhatsApp contact. Tracks AIDA funnel stage, opt-in consent, and in-progress guided booking state.';

drop trigger if exists whatsapp_conversations_set_updated_at on public.whatsapp_conversations;
create trigger whatsapp_conversations_set_updated_at
  before update on public.whatsapp_conversations
  for each row execute procedure public.set_updated_at();

-- ============================================================================
-- WHATSAPP FUNNEL EVENTS
-- Append-only event log — this is what funnel/conversion metrics and
-- "how many contacts ever reached stage X" queries are built from, rather
-- than only looking at each conversation's current stage.
-- ============================================================================
create table if not exists public.whatsapp_funnel_events (
  id                uuid primary key default gen_random_uuid(),
  conversation_id   uuid not null references public.whatsapp_conversations(id) on delete cascade,
  event_type        funnel_event_type not null,
  from_stage        funnel_stage,
  to_stage          funnel_stage,
  metadata          jsonb,
  created_at        timestamptz not null default now()
);

create index if not exists whatsapp_funnel_events_conversation_idx on public.whatsapp_funnel_events (conversation_id);
create index if not exists whatsapp_funnel_events_type_idx on public.whatsapp_funnel_events (event_type);
create index if not exists whatsapp_funnel_events_created_idx on public.whatsapp_funnel_events (created_at);

comment on table public.whatsapp_funnel_events is
  'Append-only log of every stage change / opt-in / booking / template-send event, for funnel & retargeting analytics.';

-- ============================================================================
-- WHATSAPP TEMPLATES
-- Drafts of Meta-approved "template" messages, used for retargeting contacts
-- outside the 24-hour customer-service window. Meta review/approval happens
-- outside this app (Business Manager); `status` and `meta_template_name`
-- track that lifecycle.
-- ============================================================================
create table if not exists public.whatsapp_templates (
  id                 uuid primary key default gen_random_uuid(),
  name               text not null unique,   -- internal name, snake_case (also used as the Meta template name)
  category           text not null default 'marketing' check (category in ('marketing', 'utility')),
  body               text not null,
  variables          jsonb not null default '[]'::jsonb,  -- e.g. ["patient_name"]
  target_stage       funnel_stage,            -- which funnel stage this template is meant to re-engage
  status             template_status not null default 'draft',
  meta_template_name text,

  created_by         uuid references public.staff_profiles(id),
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

comment on table public.whatsapp_templates is
  'Retargeting message templates. Drafted here, submitted to Meta for approval outside this app, status tracked here.';

drop trigger if exists whatsapp_templates_set_updated_at on public.whatsapp_templates;
create trigger whatsapp_templates_set_updated_at
  before update on public.whatsapp_templates
  for each row execute procedure public.set_updated_at();

-- ============================================================================
-- EXTEND whatsapp_messages: link every message to its conversation.
-- ============================================================================
alter table public.whatsapp_messages
  add column if not exists conversation_id uuid references public.whatsapp_conversations(id) on delete set null;

create index if not exists whatsapp_messages_conversation_idx on public.whatsapp_messages (conversation_id);

-- ============================================================================
-- ROW LEVEL SECURITY
-- Same shape as the rest of the app: any active staff can read; templates
-- (which control what gets sent to patients) are admin-write only, matching
-- how `providers` is handled. Conversations/events are written by the
-- backend via the service-role key (bypasses RLS), so the "all" policy here
-- is mainly about what staff can see/do from a future direct client query.
-- ============================================================================
alter table public.whatsapp_conversations  enable row level security;
alter table public.whatsapp_funnel_events  enable row level security;
alter table public.whatsapp_templates      enable row level security;

drop policy if exists whatsapp_conversations_all on public.whatsapp_conversations;
create policy whatsapp_conversations_all on public.whatsapp_conversations
  for all using (public.is_active_staff()) with check (public.is_active_staff());

drop policy if exists whatsapp_funnel_events_read on public.whatsapp_funnel_events;
create policy whatsapp_funnel_events_read on public.whatsapp_funnel_events
  for select using (public.is_active_staff());

drop policy if exists whatsapp_templates_read on public.whatsapp_templates;
create policy whatsapp_templates_read on public.whatsapp_templates
  for select using (public.is_active_staff());

drop policy if exists whatsapp_templates_write on public.whatsapp_templates;
create policy whatsapp_templates_write on public.whatsapp_templates
  for all using (
    exists (select 1 from public.staff_profiles where id = auth.uid() and role = 'admin')
  ) with check (
    exists (select 1 from public.staff_profiles where id = auth.uid() and role = 'admin')
  );
