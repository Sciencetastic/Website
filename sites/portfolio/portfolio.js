/* Portfolio mode switcher: reorders + emphasises the same content, never hides a mode.
   URL: ?mode=pm | ?mode=indie | ?mode=academic (no param = All). */
(function () {
  "use strict";
  var ORDER = {
    all:      ["hero", "about", "results", "work", "indie", "writing", "credentials", "skills", "press", "contact"],
    pm:       ["hero", "about", "results", "work", "credentials", "skills", "indie", "writing", "press", "contact"],
    indie:    ["hero", "about", "indie", "press", "writing", "work", "skills", "credentials", "results", "contact"],
    academic: ["hero", "about", "credentials", "skills", "work", "indie", "writing", "results", "press", "contact"]
  };
  var NOTES = {
    all: "Showing everything. Pick a view to put the most relevant work first — nothing is hidden.",
    pm: "Corporate PM view: Microsoft, Amazon, Full Swing Golf and 343 Industries first. Everything else is still below.",
    indie: "Indie Game view: SuckerFree games, awards and trailers first. Corporate roles are still below.",
    academic: "Academic & Certifications view: degrees and certifications first. Work history is still below."
  };
  var SKILL_DEFAULT = { all: "all", pm: "pm", indie: "eng", academic: "all" };
  var WORK_NOTE = {
    all: "All roles, most recent first.",
    pm: "Corporate program and project roles first, then other experience.",
    indie: "Game-industry roles first, then other experience.",
    academic: "All roles, most recent first."
  };

  var body = document.body;
  var sections = {};
  document.querySelectorAll("[data-section]").forEach(function (s) { sections[s.getAttribute("data-section")] = s; });
  var jobs = Array.prototype.slice.call(document.querySelectorAll("#timeline .job"));

  function setSkillFilter(cat) {
    document.querySelectorAll("[data-skill-filter]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-skill-filter") === cat));
    });
    document.querySelectorAll("#skills-list li").forEach(function (li) {
      li.hidden = !(cat === "all" || li.getAttribute("data-cat") === cat);
    });
  }

  function applyMode(mode, push) {
    if (!ORDER[mode]) mode = "all";
    body.setAttribute("data-mode", mode);
    ORDER[mode].forEach(function (key, i) { if (sections[key]) sections[key].style.order = i; });

    var primaryCount = 0, firstSecondary = null;
    var sorted = jobs.slice().sort(function (a, b) {
      var am = matches(a, mode), bm = matches(b, mode);
      if (am !== bm) return am ? -1 : 1;
      return a.getAttribute("data-rank") - b.getAttribute("data-rank");
    });
    sorted.forEach(function (job, i) {
      var m = matches(job, mode);
      job.style.order = i;
      job.classList.toggle("is-secondary", !m);
      job.classList.remove("is-first-secondary");
      if (m) primaryCount++; else if (!firstSecondary) firstSecondary = job;
    });
    if (firstSecondary && primaryCount) firstSecondary.classList.add("is-first-secondary");

    document.querySelectorAll("[data-mode-btn]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-mode-btn") === mode));
    });
    document.getElementById("mode-note").textContent = NOTES[mode];
    document.getElementById("work-note").textContent = WORK_NOTE[mode];
    setSkillFilter(SKILL_DEFAULT[mode]);

    if (push) {
      var url = new URL(location.href);
      if (mode === "all") url.searchParams.delete("mode"); else url.searchParams.set("mode", mode);
      history.replaceState(null, "", url);
    }
  }

  function matches(job, mode) {
    if (mode === "all" || mode === "academic") return true;
    return (" " + job.getAttribute("data-modes") + " ").indexOf(" " + mode + " ") !== -1;
  }

  document.querySelectorAll("[data-mode-btn]").forEach(function (b) {
    b.addEventListener("click", function () { applyMode(b.getAttribute("data-mode-btn"), true); });
  });
  document.querySelectorAll("[data-skill-filter]").forEach(function (b) {
    b.addEventListener("click", function () { setSkillFilter(b.getAttribute("data-skill-filter")); });
  });
  document.getElementById("print-btn").addEventListener("click", function () { window.print(); });

  var initial = new URLSearchParams(location.search).get("mode") || "all";
  applyMode(initial, false);
})();
