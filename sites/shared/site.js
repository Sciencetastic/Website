/* Shared behaviour for all 4 sites: form handling + click-to-load video. */
(function () {
  "use strict";
  var cfg = window.SITE_FORMS || { MODE: "mailto", FORMSPREE_IDS: {} };
  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

  function pickMode(list) {
    var m = cfg.MODE || "auto";
    if (m !== "auto") return m;
    if (/\.netlify\.app$/i.test(location.hostname) || cfg.NETLIFY_CUSTOM_DOMAIN) return "netlify";
    if (cfg.FORMSPREE_IDS && cfg.FORMSPREE_IDS[list]) return "formspree";
    return "mailto";
  }

  function setStatus(form, kind, msg) {
    var el = form.querySelector(".form-status");
    if (!el) return;
    el.className = "form-status is-" + kind;
    el.textContent = msg;
    el.focus && el.focus();
  }

  function fieldErr(input, msg) {
    var id = input.getAttribute("aria-describedby");
    var box = id && document.getElementById(id.split(" ")[0]);
    if (box) box.textContent = msg || "";
    if (msg) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid");
  }

  function validate(form) {
    var ok = true, first = null;
    var email = form.querySelector('input[type="email"]');
    var consent = form.querySelector('input[name="consent"]');
    if (email) {
      var v = email.value.trim();
      if (!EMAIL_RE.test(v)) { fieldErr(email, v ? "Please enter a valid email address." : "Email is required."); ok = false; first = first || email; }
      else fieldErr(email, "");
    }
    if (consent) {
      if (!consent.checked) { fieldErr(consent, "Please tick the consent box to sign up."); ok = false; first = first || consent; }
      else fieldErr(consent, "");
    }
    if (first) first.focus();
    return ok;
  }

  function summary(form) {
    var fd = new FormData(form), lines = [];
    fd.forEach(function (val, key) {
      if (key === "bot-field" || key === "form-name") return;
      lines.push(key + ": " + val);
    });
    return lines.join("\n");
  }

  function mailtoFallback(form, list) {
    var to = cfg.FALLBACK_USER + "@" + cfg.FALLBACK_DOMAIN;
    var subject = "[" + list + "] sign-up from website";
    var href = "mailto:" + to + "?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(summary(form));
    setStatus(form, "warn", "Opening your email app with your details filled in — please press Send there to finish. (The online form service is not connected yet.)");
    window.location.href = href;
  }

  function onSubmit(e) {
    var form = e.currentTarget;
    e.preventDefault();
    if (form.querySelector('[name="bot-field"]').value) return; // honeypot
    if (!validate(form)) { setStatus(form, "err", "Please fix the highlighted fields."); return; }
    var list = form.getAttribute("data-list");
    var mode = pickMode(list);
    var btn = form.querySelector('button[type="submit"]');
    if (mode === "mailto") return mailtoFallback(form, list);

    btn.disabled = true;
    var req;
    if (mode === "netlify") {
      req = fetch("/", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams(new FormData(form)).toString()
      });
    } else {
      req = fetch("https://formspree.io/f/" + cfg.FORMSPREE_IDS[list], {
        method: "POST", headers: { Accept: "application/json" }, body: new FormData(form)
      });
    }
    req.then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      form.reset();
      setStatus(form, "ok", form.getAttribute("data-success") || "Thanks — you're on the list.");
    }).catch(function () {
      setStatus(form, "err", "Sorry, that didn't send. Opening your email app instead…");
      setTimeout(function () { mailtoFallback(form, list); }, 900);
    }).finally(function () { btn.disabled = false; });
  }

  document.querySelectorAll("form.signup[data-list]").forEach(function (f) {
    f.setAttribute("novalidate", "");
    f.addEventListener("submit", onSubmit);
  });

  /* Click-to-load YouTube (privacy-enhanced domain, nothing loads until clicked) */
  document.querySelectorAll(".video[data-yt]").forEach(function (box) {
    var btn = box.querySelector(".video-play");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var f = document.createElement("iframe");
      f.src = "https://www.youtube-nocookie.com/embed/" + box.getAttribute("data-yt") + "?autoplay=1";
      f.title = box.getAttribute("data-title") || "Video";
      f.allow = "autoplay; encrypted-media; picture-in-picture";
      f.allowFullscreen = true;
      box.innerHTML = "";
      box.appendChild(f);
    });
  });

  var y = document.querySelectorAll("[data-year]");
  y.forEach(function (el) { el.textContent = new Date().getFullYear(); });
})();
