# William McDonald — portfolio + 3 promo sites

This repo holds two things:

- **`sites/`** — four static websites sharing one design system (this README).
- `app/`, `mst/`, `tools/`, `out/` — the NES art / NES Maker tools (see `app/README.md`).

| Site | Folder | What it is |
|---|---|---|
| Portfolio | `sites/portfolio/` | Morphable résumé: All / Corporate PM / Indie Game / Academic views (`?mode=pm`, `?mode=indie`, `?mode=academic`), one-click print-to-PDF résumé, contact form |
| From Beyond: Prologue — cartridges | `sites/prologue-cartridges/` | Kickstarter notify list for the Nintendo / Genesis / Game Boy-GBC ports |
| From Beyond: The Dinner Party | `sites/dinner-party/` | Sequel teaser + beta/demo sign-up |
| Spirit Board: The Séance (working title) | `sites/tarot-reader/` | Electronic tarot board game prototype + interest list |
| Shared | `sites/shared/` | `base.css` (design tokens + components), `site.js` (forms, video), `config.js` (form settings), `img/` |

Plain HTML/CSS/JS. **No build step, no dependencies, no database.**

## Preview locally

```bash
cd sites && python3 -m http.server 8000
```

Then open http://localhost:8000/portfolio/

## Deploy free on Netlify (recommended — forms work automatically)

1. Sign in at https://app.netlify.com (free, no card) → **Add new site → Import an existing project** → pick this GitHub repo. `netlify.toml` already sets the publish folder to `sites` with no build command. (Or drag the `sites/` folder onto https://app.netlify.com/drop.)
2. After the first deploy, go to **Site configuration → Forms** and click **Enable form detection**, then redeploy once. Four forms appear: `portfolio-contact`, `prologue-cartridge-notify`, `dinner-party-beta`, `tarot-interest`.
3. **Forms → Form notifications → Add notification → Email notification** → event “New form submission”, form “Any form”, email **w.arthur.mcdonald@gmail.com**. Each email's subject names the form, so the four lists stay separate.
4. Send one test submission per form and check the inbox.
5. Replace `https://YOUR-SITE.netlify.app` in `sites/sitemap.xml` and `sites/robots.txt` with the real URL.

URLs will be `https://<your-site>.netlify.app/portfolio/`, `/prologue-cartridges/`, `/dinner-party/`, `/tarot-reader/` (the root redirects to the portfolio).

If you later add a custom domain, set `NETLIFY_CUSTOM_DOMAIN: true` in `sites/shared/config.js`.

### Alternative: Formspree (works on any host, incl. GitHub Pages)
Create 4 free forms at https://formspree.io pointed at w.arthur.mcdonald@gmail.com, paste each form ID into `FORMSPREE_IDS` in `sites/shared/config.js`, and set `MODE: "formspree"`.

### Fallback (what happens before either is set up)
If no form service is connected, submitting a form opens the visitor's email app with a pre-filled message addressed to the project inbox and the list name in the subject (e.g. `[tarot-interest] sign-up from website`). This is a **fallback** — it relies on the visitor pressing Send.

## Export subscriber lists (Netlify)
1. Netlify dashboard → your site → **Forms**.
2. Click the form (e.g. `prologue-cartridge-notify`).
3. Click **Download as CSV**. (Formspree: form → Submissions → Export → CSV.)

## Editing placeholders
Every unknown is marked `[TBD …]` on the page (yellow dashed label). Search the `sites/` folder for `TBD`, or see **`TBD.md`** for the full list with file + line. Replace the whole `<span class="tbd">…</span>` with the real text.

Image swaps are listed in **`ASSETS.md`**; sources in **`SOURCES.md`**.

## Not in this build (by design)
No MERN backend, no Kickstarter/BackerKit/payment integration, no prices or dates, no tracking scripts. YouTube trailers load only when clicked (privacy-enhanced domain).
