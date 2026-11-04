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

## Check & preview locally

```bash
python3 scripts/check_links.py sites
```


```bash
cd sites && python3 -m http.server 8000
```

Then open http://localhost:8000/portfolio/

## Deploy — pick ONE option

### Option A — Netlify (recommended: forms work with zero code changes)
1. Sign in at https://app.netlify.com with your GitHub account (free, no card).
2. **Add new site → Import an existing project → GitHub → Sciencetastic/Website.** Branch: the one this PR merges into. `netlify.toml` already sets publish folder `sites`, no build command. Click **Deploy**.
3. **Site configuration → Forms → Enable form detection**, then **Deploys → Trigger deploy → Deploy site** once. Four forms appear: `portfolio-contact`, `prologue-cartridge-notify`, `dinner-party-beta`, `tarot-interest`.
4. **Forms → Form notifications → Add notification → Email notification** → event *New form submission*, form *Any form*, email **w.arthur.mcdonald@gmail.com**. The email subject names the form, so the four lists stay separate.
5. Send **one** test per form (4 total) and confirm each arrives.
6. Replace `https://YOUR-SITE.netlify.app` in `sites/sitemap.xml` and `sites/robots.txt` with your real URL.

Live URLs: `https://<name>.netlify.app/portfolio/`, `/prologue-cartridges/`, `/dinner-party/`, `/tarot-reader/` (root redirects to the portfolio).

### Option B — GitHub Pages (already wired up; forms need Formspree)
The workflow `.github/workflows/pages.yml` checks every internal link and deploys `sites/` automatically.
1. Repo **Settings → Pages → Build and deployment → Source: GitHub Actions**. (This is the one step a workflow is not allowed to do for you.)
2. Merge the PR into the default branch (or **Actions → "Sites — check & deploy" → Run workflow** on the default branch).
3. Site goes live at **https://sciencetastic.github.io/Website/portfolio/** (and `/prologue-cartridges/`, `/dinner-party/`, `/tarot-reader/`).
4. Forms: GitHub Pages can't receive form posts, so sign up free at https://formspree.io (no card), create 4 forms that email **w.arthur.mcdonald@gmail.com**, paste each form ID into `FORMSPREE_IDS` in `sites/shared/config.js`, commit. Then send one test per form.
5. Replace `https://YOUR-SITE.netlify.app` in `sites/sitemap.xml` and `sites/robots.txt` with `https://sciencetastic.github.io/Website`.

If you later put a custom domain on Netlify, set `NETLIFY_CUSTOM_DOMAIN: true` in `sites/shared/config.js`.

### Fallback (what happens before a form service is connected)
Submitting opens the visitor's email app with a pre-filled message to the project inbox and the list name in the subject (e.g. `[tarot-interest] sign-up from website`). It works, but relies on the visitor pressing Send — so connect Netlify or Formspree before promoting the sites.

## Export subscriber lists (Netlify)
1. Netlify dashboard → your site → **Forms**.
2. Click the form (e.g. `prologue-cartridge-notify`).
3. Click **Download as CSV**. (Formspree: form → Submissions → Export → CSV.)

## Editing placeholders
Every unknown is marked `[TBD …]` on the page (yellow dashed label). Search the `sites/` folder for `TBD`, or see **`TBD.md`** for the full list with file + line. Replace the whole `<span class="tbd">…</span>` with the real text.

Image swaps are listed in **`ASSETS.md`**; sources in **`SOURCES.md`**.

## Not in this build (by design)
No MERN backend, no Kickstarter/BackerKit/payment integration, no prices or dates, no tracking scripts. YouTube trailers load only when clicked (privacy-enhanced domain).
