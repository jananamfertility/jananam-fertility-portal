# Jananam Fertility Centre — Appointment Booking Portal

A small internal booking portal for front-office staff: a calendar of
appointments (consultation / follow-up / NT scan), with add/edit/delete,
built for the clinic's actual volume (roughly 40–65 bookings/month, 3–4 a
day, up to 8 on Saturdays).

## Architecture

```
frontend/   React + TypeScript (Vite), calendar UI, talks to the backend API
backend/    FastAPI, verifies Supabase-authenticated users, is the only
            thing that touches the database
supabase/   SQL migration(s) — schema, Row Level Security, seed data
```

- **Auth**: each front-office user gets their own Supabase Auth login
  (email + password). The frontend signs in via `supabase-js` and sends
  the resulting access token to the backend on every request.
- **Backend**: FastAPI verifies that token, confirms the user is an
  active row in `staff_profiles`, and then reads/writes the database
  using the Supabase **service role** key. Row Level Security is enabled
  on every table as defense-in-depth even though the API is the normal
  path in.
- **Database**: plain Postgres tables via Supabase — `patients`,
  `providers`, `appointments`, `staff_profiles`, plus a `whatsapp_messages`
  table that exists now but is unused until phase 2.
- **Admin panel**: staff with role `admin` see an extra "Admin" tab
  (`/api/staff`, `/api/providers` writes, `/api/reports/summary`) for
  managing the doctor/provider list, creating and deactivating staff
  logins, and viewing monthly booking reports. Front-office-only staff
  don't see this tab.
- **WhatsApp (phase 2)**: `POST /api/webhooks/whatsapp` already exists,
  verifies Meta's request signature, and logs every inbound message,
  matched to a patient by phone number where possible. Turning on actual
  auto-booking from WhatsApp is additive — see [Phase 2](#phase-2--whatsapp-activation)
  below. No schema or architecture changes will be needed to switch it on.

## One-time setup

### 1. Create the Supabase project

1. Create a project at [supabase.com](https://supabase.com).
2. In the SQL Editor, run `supabase/migrations/0001_init.sql`, then
   `0002_admin_panel.sql`, in that order. Together they create all tables,
   enums, RLS policies, a `providers` seed row you should rename, and the
   `staff_profiles.email` column the admin panel's staff list uses.
3. In **Authentication → Users**, create **one** first user (email +
   password) — this becomes your first admin. A row is auto-created for
   them in `staff_profiles` with role `front_office`; promote them with:
   ```sql
   update public.staff_profiles set role = 'admin' where id =
     (select id from auth.users where email = 'someone@example.com');
   ```
   Every other staff login can now be created from inside the app itself
   (Admin → Staff accounts) — no more trips to the Supabase dashboard for
   that.
4. Rename the seed provider (or add real ones) — this can also be done
   later from Admin → Doctors & providers:
   ```sql
   update public.providers set name = 'Dr. Actual Name', designation = 'Fertility Consultant'
     where name = 'Dr. Provider Name';
   ```
5. Grab three values from **Project Settings → API**: the Project URL, the
   `anon` public key, the `service_role` key, and (under **API → JWT
   Settings**) the JWT secret.

### 2. Configure the backend

```bash
cd backend
cp .env.example .env        # fill in SUPABASE_URL / SERVICE_ROLE_KEY / JWT_SECRET
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` for interactive API docs once it's running.

### 3. Configure the frontend

```bash
cd frontend
cp .env.example .env         # fill in VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY
npm install
npm run dev
```

Visit the URL Vite prints (typically `http://localhost:5173`), sign in with
one of the staff accounts you created, and start booking.

## Using the portal

- **Calendar** — month/week/day/agenda views. Click an empty slot to book
  a new appointment there, or click an existing appointment to edit it.
- **New / edit appointment** — search a patient by phone (existing
  patients show as suggestions) or type in a new one; the same phone
  number is always the same patient record. Pick type (Consultation /
  Follow-up / NT Scan), provider, date/time, status, and notes.
- **Delete** — from the edit view. There's no daily booking cap enforced
  (per how the clinic wanted this to work) — the calendar just shows
  everything booked for the day so front office can eyeball how full it
  is.
- **Colors** — each appointment type has its own color; completed/no-show/
  cancelled appointments are shown faded rather than removed, so the day's
  history stays visible.
- **Admin tab** (visible only to `admin`-role staff):
  - *Doctors & providers* — add a provider, deactivate one instead of
    deleting it (keeps past appointments intact).
  - *Staff accounts* — create a front-office or admin login directly
    (creates the Supabase Auth user and its `staff_profiles` row in one
    step), deactivate an account, or change someone's role. An admin can't
    deactivate or demote their own account — that needs a second admin.
  - *Reports* — pick a month to see total bookings, the kept vs.
    cancelled/no-show rate, and breakdowns by appointment type, status, day
    of week (to track against the 3–4/weekday, up to 8/Saturday pattern),
    and provider.

## Deploying

This repo doesn't bake in a specific host. In practice:
- **Backend**: any place that runs a Python ASGI app (Render, Railway, Fly.io,
  a small VM behind Nginx) — set the same env vars as `.env`.
- **Frontend**: any static host (Netlify, Vercel, Cloudflare Pages, or
  served by the same VM) — build with `npm run build`, deploy the `dist/`
  folder, set the same env vars at build time.
- Update `CORS_ORIGINS` in the backend's env to the deployed frontend URL,
  and `VITE_API_BASE_URL` in the frontend's env to the deployed backend URL.

## Phase 2 — WhatsApp activation

The webhook endpoint and message log already exist
(`backend/app/routers/webhooks.py`, `whatsapp_messages` table). To switch
on WhatsApp booking when you're ready:

1. Create a Meta App with the WhatsApp product, get a phone number
   connected via the Cloud API.
2. Set `WHATSAPP_VERIFY_TOKEN` (any string you choose) and
   `WHATSAPP_APP_SECRET` (from the Meta App dashboard) in the backend's
   `.env`, then register `https://your-api-host/api/webhooks/whatsapp` as
   the webhook URL in the Meta App dashboard — it will call the `GET`
   handler already in this repo to verify itself.
3. Inbound messages will start flowing into `whatsapp_messages` and (if
   the phone number is already a known patient) get linked to them
   automatically — nothing else to build for that part.
4. To actually create appointments from WhatsApp messages (rather than
   just logging them), implement the `TODO` block inside
   `receive_webhook()` in `webhooks.py`: parse the inbound message (or
   drive a structured button/list-message flow), reuse the same logic as
   `POST /api/appointments` with `source="whatsapp"`, and send a
   confirmation back using the Cloud API's `/messages` endpoint (needs a
   permanent access token + phone number ID — add those to
   `app/config.py` when you build this out).

No database migration or frontend change is required for step 4 — the
`source` and `whatsapp_message_id` columns on `appointments`, and the
`whatsapp_messages` table, are already there.

## Project structure reference

```
backend/
  app/
    main.py          FastAPI app, CORS, router wiring, /api/health
    config.py         env-driven settings
    database.py       Supabase client (service role)
    auth.py            verifies Supabase JWTs, loads staff_profiles
    schemas.py          Pydantic request/response models
    routers/
      patients.py        search / create / update patients
      providers.py        list providers, admin-only create/update
      appointments.py      the core calendar CRUD
      webhooks.py           phase-2 WhatsApp webhook (stub, see above)
      staff.py               admin-only: list/create/update staff accounts
      reports.py              booking stats aggregation
frontend/
  src/
    lib/
      supabaseClient.ts    Supabase Auth client
      api.ts                 axios client, attaches the auth token
      types.ts                shared TS types
    context/AuthContext.tsx  session state + staff profile/role, sign in/out
    pages/
      LoginPage.tsx
      CalendarPage.tsx        react-big-calendar view + filters
      AdminPage.tsx            Reports / Providers / Staff sub-tabs
    components/
      AppHeader.tsx             shared header + Calendar/Admin nav
      AppointmentModal.tsx      create/edit/delete form
      admin/
        ProvidersAdmin.tsx
        StaffAdmin.tsx
        ReportsAdmin.tsx
supabase/migrations/
  0001_init.sql
  0002_admin_panel.sql
```
