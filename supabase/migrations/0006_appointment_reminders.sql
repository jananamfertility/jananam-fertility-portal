-- Jananam Fertility Centre — appointment reminders (see KNOWN_GAPS.md,
-- "No appointment reminders, despite promising them"). Adds the column the
-- reminder script (backend/scripts/send_reminders.py) uses to avoid
-- reminding the same appointment twice, and registers the reminder message
-- as a WhatsApp template row so it shows up in the admin portal's
-- Marketing > Templates list alongside retargeting templates.
--
-- The template itself still needs to be created and submitted for review
-- in Meta Business Manager by hand (there's no API for that in this
-- codebase — see KNOWN_GAPS.md) using the exact body text below, under the
-- name "appointment_reminder_24h", category UTILITY. The reminder script
-- checks Meta's live approval status before every run and sends nothing
-- until that's done.

alter table public.appointments
  add column if not exists reminder_sent_at timestamptz;

comment on column public.appointments.reminder_sent_at is
  'Set the moment a WhatsApp reminder send was attempted for this appointment, so it is only ever reminded once. See backend/scripts/send_reminders.py.';

insert into public.whatsapp_templates (name, category, body, variables, target_stage, status, meta_template_name)
select
  'Appointment Reminder (24h before)',
  'utility',
  'Hi {{1}}, this is a reminder from Jananam Fertility Centre about your {{2}} appointment on {{3}} at {{4}}. Reply here if you need to reschedule or have questions.',
  '["patient_first_name","appointment_type","date","time"]'::jsonb,
  null,
  'draft',
  'appointment_reminder_24h'
where not exists (
  select 1 from public.whatsapp_templates where meta_template_name = 'appointment_reminder_24h'
);
