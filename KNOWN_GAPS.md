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

## Review — 2026-09-12 (persona + conversational-quality pass)

Prompted by adding the Asha persona, source-page personalization, and
nurturing behavior. Covers what was fixed alongside that work, plus a
fresh look at what's still missing for "personalized and intuitive."

### Fixed in this pass

- [x] **WhatsApp Graph API version was 6 weeks from expiring.** `v20.0`
  (pinned in `whatsapp_client.py`) expires **September 24, 2026** per
  Meta's 2-year version window -- unrelated to anything asked for, but
  would have silently broken every outbound WhatsApp call. Bumped to
  `v26.0`.
- [x] **No typing indicator / read receipt.** Added
  `whatsapp_client.mark_read_with_typing()`, called as early as possible
  in the webhook handler -- patients now see blue ticks + "typing..." while
  the AI composes a reply, instead of dead air.
- [x] **Unrecognized interactive taps went silent.** A stale/expired
  button tap only logged a warning server-side; the patient got no reply
  at all. Now sends a "that option isn't available -- reply MENU" fallback.
- [x] **Non-text messages (photos, voice notes, documents, location,
  etc.) were silently dropped.** `handle_inbound_message` only ever looked
  at `message.text.body`; anything else fell through to `if not body_text:
  return` with zero reply. Now acknowledges it and asks them to type
  instead.
- [x] **`get_or_create_conversation` returned a stale dict.** When a
  returning contact's `display_name` was just backfilled from their
  WhatsApp profile, the function updated the row but hadn't updated the
  in-memory dict it returned -- so that name was invisible to the rest of
  that request. Harmless today (nothing reads `display_name` yet -- see
  the open item below) but would have silently broken personalization the
  moment something started using it.
- [x] **Migration history had drifted from the live schema.** `source_context`
  and `messages_since_menu` were added directly on the live Supabase
  project via the Supabase MCP, with no matching file checked into
  `supabase/migrations/`. Added `0005_persona_and_context.sql` so a
  fresh/staging database built from migrations alone wouldn't come up
  missing these columns.

### Open -- for "more personalized and intuitive," needs your call

- [ ] **No appointment reminders, despite promising them.** The very
  opt-in message a patient agrees to says "reply YES to allow us to send
  appointment reminders" -- nothing in the codebase actually sends one.
  There's no scheduled/cron infrastructure at all yet. This is the single
  biggest gap between what the bot claims and what it does. Needs: a
  scheduled job (e.g. a Render Cron Job) that finds appointments starting
  in the next N hours and messages the patient, plus (since reminders are
  typically sent outside the 24-hour free-form window) an approved Meta
  message template rather than plain text.
- [ ] **Asha never uses the patient's name.** `display_name` (the WhatsApp
  profile name) is captured but never surfaced in any message -- every
  reply, including the welcome message, is generic. The risk: a WhatsApp
  profile name isn't always a real, presentable first name (emoji,
  nicknames, a shared family/business name), so using it uncritically
  could occasionally read as odd rather than warm. Fixable with a sanity
  filter (only use it if it looks like a plausible name), but that's a
  judgment call on tone, not a pure bug fix.
- [ ] **No patient-history awareness in the AI conversation.** Once
  someone has booked before, Asha still starts from a blank slate each
  time -- she only sees the last 10 messages, never whether this contact
  already has an upcoming or past appointment (that only surfaces if they
  explicitly type "my appointments"). A truly intuitive assistant would
  notice a returning, already-booked patient and talk accordingly ("how
  did your consultation go?").
- [ ] **English only.** Chennai has a large Tamil- and Hindi-speaking
  population; the bot only operates in English. The AI model itself is
  polyglot, but the static menu/button text (main menu, booking flow,
  info panels) is all hardcoded English strings that would need
  duplicating per language, plus a way to detect/switch -- a real project,
  not a quick fix.
- [ ] **Webhook processes everything synchronously, including the AI
  call.** Meta expects a webhook to acknowledge within roughly 10 seconds
  or it's treated as a failed delivery and retried; the OpenRouter call in
  this webhook has a 30-second timeout. The `wa_message_id` unique
  constraint already prevents a slow-but-successful reply from being sent
  twice on a Meta retry, but sustained slow AI responses could still get
  this integration flagged as unreliable by Meta over time. Best practice
  is to acknowledge the webhook immediately and do the actual work in a
  background task -- a real architecture change (needs a task queue or
  background-task runner), so flagging rather than changing unprompted.

---
*Last updated: 2026-09-12.*
