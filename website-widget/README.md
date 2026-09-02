# WhatsApp chat button — website embed

`whatsapp-button-embed.html` is a floating WhatsApp button for your website
(bottom-right corner). Clicking it opens WhatsApp with a pre-filled greeting,
starting a conversation with the bot.

## 1. Edit the number

Open `whatsapp-button-embed.html` and change `91XXXXXXXXXX` in the `href` to
your clinic's WhatsApp Business number — international format, digits only,
no `+`, no spaces (e.g. `919812345678` for `+91 98123 45678`). This must be
the same number connected to the WhatsApp Business Cloud API (see the
backend README's "WhatsApp bot setup" section).

## 2. Paste it into your site

**Wix:** Editor → Add (+) → Embed → Embed Code → **Embed HTML**. Paste the
whole file's contents in, then set the element to fixed position (or just
leave it — the snippet already positions itself with `position: fixed`, so
size/position of the embed box on the page doesn't matter). Publish.

**WordPress:** Add a **Custom HTML** block (in the page/post editor) and
paste the contents in, or — to have it on every page — paste it into your
theme's footer via Appearance → Theme File Editor → `footer.php` just
before `</body>`, or a "Insert Header/Footer Code" plugin if your theme
doesn't allow direct edits.

**Shopify:** Online Store → Themes → **Edit code** → open `theme.liquid` →
paste the snippet just before `</body>` → Save.

**Any other builder:** look for "Embed HTML", "Custom Code", or "Embed
widget" — nearly every builder has one.

## 3. Test it

Open the site, click the button, confirm it opens WhatsApp with the clinic's
number and the greeting pre-filled. Send it — you should get the bot's
welcome message back within a few seconds (once the backend's WhatsApp
credentials are configured; see the main README).
