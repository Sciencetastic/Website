/* Planchette drifts toward the pointer over the hero board. Skipped for reduced-motion and touch-only devices. */
(function () {
  "use strict";
  var hero = document.getElementById("board");
  var p = document.getElementById("planchette");
  if (!hero || !p) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (!window.matchMedia("(hover: hover)").matches) return;
  hero.addEventListener("pointermove", function (e) {
    var r = hero.getBoundingClientRect();
    p.style.left = (e.clientX - r.left) + "px";
    p.style.top = (e.clientY - r.top) + "px";
    p.classList.add("is-on");
  });
  hero.addEventListener("pointerleave", function () { p.classList.remove("is-on"); });
})();
