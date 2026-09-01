-- Jananam Fertility Centre — Appointment Booking Portal
-- Initial schema migration
-- Run this in the Supabase SQL editor, or via `supabase db push` /
-- `psql "$SUPABASE_DB_URL" -f 0001_init.sql`

-- ============================================================================
-- EXTENSIONS
-- ============================================================================
create extension if not exists "pgcrypto"; -- gen_random_uuid()

-- ============================================================================
-- ENUMS
-- ============================================================================
do $$ begin
  create type appointment_type as enum ('consultation', 'follow_up', 'nt_scan');
exception when duplicate_object then null; end $$;

do $$ begin
  create type appointment_status as enum (
    'scheduled', 'confirmed', 'completed', 'no_show', 'cancelled'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type appointment_source as enum ('manual', 'whatsapp');
exception when duplicate_object then null; end $$;

do $$ begin
  create type staff_role as enum ('front_office', 'admin');
exception when duplicate_object then null; end $$;

-- ============================================================================
-- STAFF PROFILES
-- One row per Supabase Auth user (auth.users). Created via a trigger when a
-- new user signs up, or manually by an admin using the SQL editor / API.
-- ============================================================================
create table if not exists public.staff_profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  full_name   text not null,
  role        staff_role not null default 'front_office',
  is_active   boolean not null default true,
  created_at  timestamptz not null default now()
);

comment on table public.staff_profiles is
  'Front-office / admin users of the booking portal. 1:1 with auth.users.';

-- Auto-create a staff_profiles row whenever a new auth user is created.
-- full_name is read from the signup metadata (raw_user_meta_data->>'full_name'),
-- falling back to the email local-part.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.staff_profiles (id, full_name)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1))
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- ============================================================================
-- PROVIDERS (doctors / sonographers who see patients)
-- ============================================================================
create table if not exists public.providers (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  designation text,               -- e.g. 'Fertility Consultant', 'Sonologist'
  is_active   boolean not null default true,
  created_at  timestamptz not null default now()
);

comment on table public.providers is 'Doctors / providers appointments can be booked with.';

-- ============================================================================
-- PATIENTS
-- Kept as a lightweight, de-duplicated directory (by phone number) so the
-- same patient's appointment history can be tracked, and so a future
-- WhatsApp webhook (phase 2) can match inbound messages to an existing
-- patient by phone number.
-- ============================================================================
create table if not exists public.patients (
  id            uuid primary key default gen_random_uuid(),
  full_name     text not null,
  phone         text not null,
  age           int,
  partner_name  text,
  notes         text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create unique index if not exists patients_phone_key on public.patients (phone);
comment on table public.patients is
  'Patient directory, de-duplicated by phone. Phone is the join key phase-2 WhatsApp matching will use.';

-- ============================================================================
-- APPOINTMENTS
-- ============================================================================
create table if not exists public.appointments (
  id              uuid primary key default gen_random_uuid(),
  patient_id      uuid not null references public.patients(id) on delete cascade,
  provider_id     uuid references public.providers(id) on delete set null,

  appointment_type appointment_type not null,
  status            appointment_status not null default 'scheduled',

  starts_at       timestamptz not null,
  ends_at         timestamptz not null,

  notes           text,

  -- Phase 2 (WhatsApp) readiness — populated by manual booking today,
  -- and by the WhatsApp webhook once phase 2 is switched on.
  source                appointment_source not null default 'manual',
  whatsapp_message_id   text,   -- id of the inbound WA message that created/changed this booking

  created_by      uuid references public.staff_profiles(id),
  updated_by      uuid references public.staff_profiles(id),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),

  constraint appointments_time_order check (ends_at > starts_at)
);

create index if not exists appointments_starts_at_idx on public.appointments (starts_at);
create index if not exists appointments_patient_idx on public.appointments (patient_id);
create index if not exists appointments_provider_idx on public.appointments (provider_id);
create index if not exists appointments_status_idx on public.appointments (status);

comment on table public.appointments is
  'Core booking table. source/whatsapp_message_id exist now so phase-2 WhatsApp bookings need no schema change.';

-- keep updated_at fresh
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists appointments_set_updated_at on public.appointments;
create trigger appointments_set_updated_at
  before update on public.appointments
  for each row execute procedure public.set_updated_at();

drop trigger if exists patients_set_updated_at on public.patients;
create trigger patients_set_updated_at
  before update on public.patients
  for each row execute procedure public.set_updated_at();

-- ============================================================================
-- WHATSAPP MESSAGES (phase 2 — table exists now, unused until webhook is live)
-- Raw log of inbound/outbound WhatsApp messages, so the phase-2 webhook has
-- somewhere to land data from day one and appointments created from WhatsApp
-- are fully traceable back to the conversation that created them.
-- ============================================================================
create table if not exists public.whatsapp_messages (
  id                uuid primary key default gen_random_uuid(),
  wa_message_id     text unique,           -- WhatsApp's own message id
  direction         text not null check (direction in ('inbound', 'outbound')),
  from_phone        text not null,
  to_phone          text not null,
  body              text,
  raw_payload       jsonb,
  patient_id        uuid references public.patients(id) on delete set null,
  appointment_id    uuid references public.appointments(id) on delete set null,
  created_at        timestamptz not null default now()
);

create index if not exists whatsapp_messages_from_phone_idx on public.whatsapp_messages (from_phone);
comment on table public.whatsapp_messages is
  'Phase 2: raw WhatsApp webhook message log, linked to patients/appointments once matched.';

-- ============================================================================
-- ROW LEVEL SECURITY
-- Any authenticated staff member (row in staff_profiles, is_active = true)
-- can read/write clinic data. Patients never authenticate directly in v1,
-- so there is no patient-facing policy.
-- ============================================================================
alter table public.staff_profiles   enable row level security;
alter table public.providers        enable row level security;
alter table public.patients         enable row level security;
alter table public.appointments     enable row level security;
alter table public.whatsapp_messages enable row level security;

create or replace function public.is_active_staff()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.staff_profiles
    where id = auth.uid() and is_active = true
  );
$$;

-- staff_profiles: a user can read all staff, but only update their own row;
-- inserts happen via the trigger only.
drop policy if exists staff_read on public.staff_profiles;
create policy staff_read on public.staff_profiles
  for select using (public.is_active_staff());

drop policy if exists staff_update_self on public.staff_profiles;
create policy staff_update_self on public.staff_profiles
  for update using (id = auth.uid()) with check (id = auth.uid());

-- providers: any active staff can read; only admins can write.
drop policy if exists providers_read on public.providers;
create policy providers_read on public.providers
  for select using (public.is_active_staff());

drop policy if exists providers_write on public.providers;
create policy providers_write on public.providers
  for all using (
    exists (select 1 from public.staff_profiles where id = auth.uid() and role = 'admin')
  ) with check (
    exists (select 1 from public.staff_profiles where id = auth.uid() and role = 'admin')
  );

-- patients / appointments / whatsapp_messages: full read/write for any active staff.
drop policy if exists patients_all on public.patients;
create policy patients_all on public.patients
  for all using (public.is_active_staff()) with check (public.is_active_staff());

drop policy if exists appointments_all on public.appointments;
create policy appointments_all on public.appointments
  for all using (public.is_active_staff()) with check (public.is_active_staff());

drop policy if exists whatsapp_messages_all on public.whatsapp_messages;
create policy whatsapp_messages_all on public.whatsapp_messages
  for all using (public.is_active_staff()) with check (public.is_active_staff());

-- ============================================================================
-- SEED DATA (safe to re-run)
-- ============================================================================
insert into public.providers (name, designation)
select 'Dr. Provider Name', 'Fertility Consultant'
where not exists (select 1 from public.providers);
