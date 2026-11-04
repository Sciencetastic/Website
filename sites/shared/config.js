/* ==========================================================================
   FORM CONFIG — the only file William needs to touch to switch form service.

   MODE options:
     "auto"      — Netlify Forms when the site is served from *.netlify.app
                   (or NETLIFY_CUSTOM_DOMAIN is true); otherwise Formspree if an
                   ID is set below; otherwise the email-client fallback.
     "netlify"   — always post to Netlify Forms.
     "formspree" — always post to Formspree (fill in the IDs below).
     "mailto"    — fallback only: opens the visitor's email app.

   Destination inbox (set inside Netlify / Formspree, NOT here):
     w.arthur.mcdonald@gmail.com
   ========================================================================== */
window.SITE_FORMS = {
  MODE: "auto",

  // Set to true once a custom domain points at the Netlify deploy.
  NETLIFY_CUSTOM_DOMAIN: false,

  // Formspree form IDs (the part after https://formspree.io/f/). Leave "" if unused.
  FORMSPREE_IDS: {
    "portfolio-contact": "",
    "prologue-cartridge-notify": "",
    "dinner-party-beta": "",
    "tarot-interest": ""
  },

  // Fallback address, split so it is not sitting in page HTML for scrapers.
  FALLBACK_USER: "w.arthur.mcdonald",
  FALLBACK_DOMAIN: "gmail.com"
};
