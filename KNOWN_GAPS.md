# WhatsApp bot — known gaps & risks

Tracked list of everything flagged as a risk or open issue on the WhatsApp
AIDA-funnel booking bot, so we're not relying on memory as we close these
out. Check items off (`[x]`) as they're fixed; each one notes why it
matters and roughly how big the fix is.

Priority order if you're not sure where to start: **P0 items first** (real
bugs / patient-facing breakage), then P1 (safety/cost exposure), then P2
(quality-of-life / measurement accuracy).

## P0 — fix before real patients use it

- [ ] **Phone number normalization mismatch.** The portal's own patient
  form normalizes numbers one way (likely bare 10-digit local format);
  WhatsApp's webhook sends the `from` field as a raw country-code-prefixed
  number (e.g. `919812345678`). If these don't match the same
  normalization, the bot will create a **duplicate patient record**
  instead of linking to an existing one, or fail to find a patient who's
  already in the system. *Fix: make one shared `normalize_phone()` used by
  both the portal form and `bot_flow.py`, and backfill/dedupe any patients
  already created via WhatsApp before this is fixed.*

- [ ] **Shared-phone / family-booking collisions.** Many patients book
  under a spouse's or parent's phone number. Right now the bot treats one
  WhatsApp number = one patient identity, so a second family member
  texting from the same number can get merged into the first person's
  record, or silently overwrite `pending_booking` mid-flow. *Fix: ask
  "who is this booking for?" as an explicit step, or at minimum let staff
  see it's flagged when a number maps to multiple people.*

- [ ] **No booking confirmation / cancel / reschedule via WhatsApp.** The
  bot can only create a new appointment — a patient can't ask "cancel my
  Thursday appointment" or "move it to Friday" through the chat; they'd
  have to call the clinic. *Fix: add a "my appointments" intent that looks
  up their upcoming bookings and offers cancel/reschedule as menu options.*

- [ ] **No double-booking / overlap check on WhatsApp bookings.** The
  guided menu only shows a day and a 15-minute slot; nothing currently
  checks that slot isn't already taken by another patient before writing
  the appointment. *Fix: reuse the same overlap check the portal's
  `AppointmentModal` (presumably) already runs before insert, inside
  `_complete_booking`.*

## P1 — safety & cost exposure

- [ ] **Emergency handling is advisory-only, no staff alert.** If a
  patient describes something urgent (bleeding, severe pain, etc.), the
  system prompt tells the AI to advise contacting the clinic/emergency
  services — but nothing pages or notifies actual staff. A message like
  that could sit unread in the conversation log. *Fix: detect an
  emergency-flagged AI response and trigger a real notification (SMS/
  email/Slack to on-call staff), not just a reply to the patient.*

- [ ] **No per-contact AI rate/spend limit.** Every free-text message from
  every WhatsApp number calls OpenRouter with no cap. A single confused or
  malicious user sending messages in a loop (or a bot doing the same) runs
  up real API spend with no ceiling. *Fix: a simple per-phone-number
  message-count or token-spend limit per hour/day, with a graceful
  fallback to the guided menu once hit.*

- [ ] **Ungrounded AI medical content, no prompt-injection defense.** The
  AI answers fertility questions from the system prompt's clinic knowledge
  plus its own training, with no retrieval against a vetted source and no
  explicit defense against a patient trying to override its instructions
  via crafted text. *Fix (lower effort first): tighten the system prompt's
  refusal/scope language and add a lightweight check for
  instruction-override patterns; (higher effort): ground medical claims in
  a fixed FAQ doc rather than open generation.*

- [ ] **Silent credential/balance expiry, no monitoring.** If the Meta
  access token expires, the WhatsApp Business number gets disconnected, or
  the OpenRouter balance runs out, the bot fails silently (falls back to
  no-op/menu-only) with nothing telling staff it happened. *Fix: a basic
  health check (e.g. hourly cron hitting a `/health/whatsapp` and
  `/health/ai` endpoint) that alerts if either integration starts
  failing.*

## P2 — quality, scale & measurement

- [ ] **Meta's pre-verification messaging caps + quality-rating risk from
  retargeting.** A new WhatsApp Business number starts on Meta's lowest
  messaging tier (very small daily limit) and quality rating can drop fast
  if retargeting sends get marked as spam/blocked by recipients. *Fix:
  ramp retargeting volume slowly, keep an eye on the number's quality
  rating in Meta Business Manager, and make sure opt-out is one word away
  (already built) so complaint rate stays low.*

- [ ] **Template-approval status is self-reported, not verified.** The
  admin UI lets staff mark a template "approved" manually; nothing checks
  against the actual Meta template-review API, so a template could be
  marked approved and sent when Meta actually rejected or is still
  reviewing it — which would fail the send outright. *Fix: use
  `whatsapp_business_account_id` to poll the real template status from
  the Graph API instead of trusting the manual flag.*

- [ ] **Funnel metric isn't a true cohort funnel.** The Marketing tab's
  funnel counts conversations currently sitting in each AIDA stage, not
  the conversion rate of a cohort moving Awareness → Interest → Desire →
  Action → Booked over time. It's a useful snapshot but shouldn't be read
  as a "40% of Interest leads become Desire" style rate yet. *Fix (when
  there's enough volume to matter): compute stage-transition rates from
  `whatsapp_funnel_events` instead of current-stage counts.*

- [ ] **No staging environment.** Every fix so far has gone straight to
  the live backend/frontend on Render and the live Supabase project —
  fine at current low volume, riskier once real patients are actively
  using WhatsApp booking daily. *Fix: a second free-tier Render
  service + Supabase branch for testing bot changes before they touch
  production, once volume justifies the overhead.*

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

---
*Last updated: 2026-09-02. This file is meant to be edited as items get
fixed — check boxes off and add notes inline rather than keeping a
separate tracker.*
