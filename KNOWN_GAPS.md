# WhatsApp bot — known gaps & risks

Tracked list of everything flagged as a risk or open issue on the WhatsApp
AIDA-funnel booking bot. Most P0/P1/P2 items below were fixed on
2026-09-02 (commit `dba28ce` locally — see the note at the bottom on
getting it onto GitHub/Render). Check off any new items as they come up;
add notes inline rather than keeping a separate tracker.

## P0 — fix before real patients use it

- [x] **Phone number normalization mismatch.** Fixed. `phone_utils.normalize_phone()`
  is now the one canonical phone shape (digits + country code, no `+`),
  used by both `PatientIn` (the portal's own patient form/API) and the
  WhatsApp webhook. Migration `0004_gap_fixes.sql` backfilled existing
  `patients.phone` values to match; any row that would've collided with
  another patient's number was left alone and logged via `NOTICE` for a
  manual look (check the migration's output if that matters to you).

- [x] **Shared-phone / family-booking collisions.** Fixed, within the
  limits of the existing schema (`patients.phone` is still unique — a true
  fix would mean separate patient records per family member sharing a
  number, which is a bigger schema change). Now: if a phone number booking
  through WhatsApp is already linked to a patient under a different name,
  the bot asks "Is this appointment for `<name>`?" before booking. A "no,
  someone else" reply still books under the same phone-linked patient
  record (unavoidable without the schema change) but flags it clearly in
  the appointment's notes for front-office review, instead of silently
  merging identities.

- [x] **No booking confirmation / cancel / reschedule via WhatsApp.** Fixed.
  Typing "MY APPOINTMENTS" (or similar) shows upcoming bookings; tapping one
  offers Cancel / Reschedule / Never mind.

- [x] **No double-booking / overlap check.** Fixed — and it turned out this
  didn't exist anywhere, not just on the WhatsApp side. `scheduling.has_overlap()`
  is now enforced on both the **portal's own appointments API** (create and
  update) and the WhatsApp booking/reschedule flow. A WhatsApp booking that
  hits a just-taken slot keeps everything else it already collected (name,
  type, provider, date) and only re-asks for a time.

## P1 — safety & cost exposure

- [x] **Emergency handling is advisory-only, no staff alert.** Partially
  fixed. A `staff_alerts` row is now created for every AI-flagged
  needs-human message, and it shows as a red banner on **every** admin
  tab (polled every 60s), not just Marketing — so it's a real, visible
  item instead of a reply sitting in the chat log. There's also an
  optional real email (`alerting.py`, via `SMTP_*` env vars) if you want
  an out-of-band ping too — it no-ops safely if left unset. This is *not*
  an SMS/phone alert — that would need a paid SMS gateway (e.g. Twilio)
  and credentials I don't have; email is the realistic middle ground for
  now given the clinic's size.

- [x] **No per-contact AI rate/spend limit.** Fixed. `AI_MAX_CALLS_PER_WINDOW`
  (default 20) per `AI_RATE_WINDOW_HOURS` (default 24) per phone number —
  once hit, the bot falls back to the guided menu instead of calling the AI.

- [x] **Ungrounded AI medical content, no prompt-injection defense.** Partially
  fixed. The system prompt now explicitly treats the patient's message as
  untrusted input and instructs the model to ignore attempts to override
  its instructions, reveal the prompt, or change its role — and messages are
  capped at 1500 characters before being forwarded to the model. This
  reduces the injection *attack surface*; it doesn't add retrieval-grounded
  medical content, which is still a larger project if you want it (a fixed,
  vetted FAQ doc the model answers from instead of open generation).

- [x] **Silent credential/balance expiry, no monitoring.** Fixed for
  visibility, not automatic paging. `GET /api/marketing/integrations-health`
  checks both WhatsApp and OpenRouter reachability; the Marketing tab shows
  live status pills. It's checked when the tab loads, not on a schedule —
  if you want a proactive page when something breaks between visits,
  that needs a scheduled check (a cron hitting this endpoint) with an
  alert channel, which isn't set up.

## P2 — quality, scale & measurement

- [~] **Meta's pre-verification messaging caps + quality-rating risk from
  retargeting.** Partially mitigated. Retargeting sends are now capped at
  200 per campaign run and paced (a short pause every 20 sends) instead of
  bursting the full list at once — re-run the campaign to reach anyone left
  over (`remaining` in the result / shown in the UI). The underlying risk
  (a new number starts on Meta's lowest tier, quality rating can still drop)
  is still something to watch manually in Meta Business Manager, especially
  early on — no code fix removes that.

- [x] **Template-approval status is self-reported, not verified.** Fixed.
  A "Sync status" button calls Meta's Graph API directly
  (`whatsapp_client.fetch_template_status`) and updates the stored status
  to match — needs `WHATSAPP_BUSINESS_ACCOUNT_ID` configured. `/retarget`
  also re-checks live status right before sending as a second check, not
  just at the point someone clicked "mark approved."

- [x] **Funnel metric isn't a true cohort funnel.** Addressed with an
  explicit caveat rather than a full per-contact cohort trace (a real one
  would need tracking each contact's stage-transition timestamps
  individually and is a bigger analytics project). The Marketing tab now
  shows stage-to-stage `conversion_rates` computed from
  `whatsapp_funnel_events`, with the UI text spelling out exactly what this
  is and isn't measuring.

- [ ] **No staging environment.** **Not done — needs your decision.** Every
  fix has gone straight to the live backend/frontend and the live Supabase
  project. Setting up staging means a second Render service (probably a
  paid instance, since the free tier is already used by production) and a
  second Supabase project — real recurring cost. Tell me if you want this
  and I'll set it up; at current volume it's a "nice to have," not urgent.

## Not a gap, just needs doing before the bot does anything

- [ ] Get WhatsApp Business Cloud API credentials from Meta (`WHATSAPP_VERIFY_TOKEN`,
  `WHATSAPP_APP_SECRET`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`,
  `WHATSAPP_BUSINESS_ACCOUNT_ID`, clinic's public number).
- [ ] Get an `OPENROUTER_API_KEY`.
- [ ] Set both sets of credentials as env vars on the `jananam-fertility-backend`
  Render service, then confirm the bot replies end-to-end on a real message.
- [ ] Replace the placeholder `91XXXXXXXXXX` number in
  `website-widget/whatsapp-button-embed.html` and paste the widget into the
  live site.
- [ ] Optional: set `SMTP_*` + `STAFF_ALERT_EMAIL_TO` if you want emergency
  alerts emailed as well as shown in the portal.

## Getting this code live

All of the above is committed locally (in your `jananam-fertility-portal`
folder) but **not yet pushed to GitHub**, because pushing needs a fresh
Personal Access Token — the one from the original setup wasn't saved
anywhere retrievable. Paste one here (GitHub → Settings → Developer
settings → Personal access tokens → generate one with `repo` scope) and
I'll push it and trigger the Render deploys. The Supabase migration
(`0004_gap_fixes.sql`) is already applied to the live database — that part
didn't need GitHub.

---
*Last updated: 2026-09-02.*
