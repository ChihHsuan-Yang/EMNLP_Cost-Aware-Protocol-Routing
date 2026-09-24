/* Cost-Aware Protocol Routing - project page behaviour.
   Vanilla JS, no dependencies. Every feature degrades to a usable page if JS
   is off: nav anchors, tables, figures and copy blocks all work without it. */
(function () {
  "use strict";

  /* ---------- 1. Scroll spy for the sticky nav ---------- */
  var navLinks = Array.prototype.slice.call(
    document.querySelectorAll('.nav-links a[href^="#"]')
  );
  var sections = navLinks
    .map(function (a) { return document.getElementById(a.getAttribute("href").slice(1)); })
    .filter(Boolean);

  if (sections.length && "IntersectionObserver" in window) {
    var visible = Object.create(null);
    var spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { visible[e.target.id] = e.isIntersecting; });
      var current = null;
      for (var i = 0; i < sections.length; i++) {
        if (visible[sections[i].id]) { current = sections[i].id; break; }
      }
      navLinks.forEach(function (a) {
        if (current && a.getAttribute("href") === "#" + current) {
          a.setAttribute("aria-current", "true");
        } else {
          a.removeAttribute("aria-current");
        }
      });
    }, { rootMargin: "-64px 0px -62% 0px", threshold: 0 });
    sections.forEach(function (s) { spy.observe(s); });
  }

  /* ---------- 2. Copy-to-clipboard for BibTeX / commands ---------- */
  Array.prototype.forEach.call(document.querySelectorAll("[data-copy]"), function (btn) {
    btn.addEventListener("click", function () {
      var target = document.getElementById(btn.getAttribute("data-copy"));
      if (!target) { return; }
      var text = target.innerText;
      var done = function () {
        var old = btn.textContent;
        btn.textContent = "Copied";
        window.setTimeout(function () { btn.textContent = old; }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () { fallback(text, done); });
      } else {
        fallback(text, done);
      }
    });
  });

  function fallback(text, done) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "-1000px";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); done(); } catch (err) { /* nothing to do */ }
    document.body.removeChild(ta);
  }

  /* ---------- 3. Lightweight in-page section search ---------- */
  var input = document.getElementById("site-search");
  var out = document.getElementById("search-results");
  if (!input || !out) { return; }

  var index = Array.prototype.map.call(document.querySelectorAll("main section[id]"), function (sec) {
    var h = sec.querySelector("h2");
    var title = h ? h.textContent.replace(/\s+/g, " ").trim() : sec.id;
    // Drop the small uppercase kicker from the searchable title.
    var kicker = h ? h.querySelector(".kicker") : null;
    if (kicker) { title = title.replace(kicker.textContent.replace(/\s+/g, " ").trim(), "").trim(); }
    var body = sec.textContent.replace(/\s+/g, " ").trim();
    return { id: sec.id, title: title, body: body, hay: (title + " " + body).toLowerCase() };
  });

  function snippet(body, q) {
    var i = body.toLowerCase().indexOf(q);
    if (i < 0) { return body.slice(0, 96) + "…"; }
    var start = Math.max(0, i - 38);
    return (start > 0 ? "…" : "") + body.slice(start, start + 116).trim() + "…";
  }

  function render(q) {
    out.innerHTML = "";
    if (q.length < 2) { out.hidden = true; return; }
    var hits = index.filter(function (s) { return s.hay.indexOf(q) !== -1; }).slice(0, 8);
    if (!hits.length) {
      var li = document.createElement("li");
      li.className = "sr-empty";
      li.textContent = "No section matches “" + q + "”";
      out.appendChild(li);
    } else {
      hits.forEach(function (s) {
        var li = document.createElement("li");
        var a = document.createElement("a");
        a.href = "#" + s.id;
        var t = document.createElement("span");
        t.className = "sr-title";
        t.textContent = s.title;
        var p = document.createElement("span");
        p.className = "sr-snip";
        p.textContent = snippet(s.body, q);
        a.appendChild(t);
        a.appendChild(p);
        a.addEventListener("click", function () { out.hidden = true; input.value = ""; });
        li.appendChild(a);
        out.appendChild(li);
      });
    }
    out.hidden = false;
  }

  input.addEventListener("input", function () { render(input.value.trim().toLowerCase()); });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { input.value = ""; out.hidden = true; input.blur(); }
    if (e.key === "ArrowDown") {
      var first = out.querySelector("a");
      if (first) { e.preventDefault(); first.focus(); }
    }
  });
  document.addEventListener("click", function (e) {
    if (!out.contains(e.target) && e.target !== input) { out.hidden = true; }
  });
})();

/* ---------------------------------------------------------------------------
   Mobile section nav.

   The list of sections is wrapped in <details class="nav-collapse">. CSS hides
   the toggle above 720px and always shows the list there, so desktop is
   unaffected. Below 720px the toggle appears; we start it CLOSED so the nav
   does not eat the first screen, and close it again after a jump so the reader
   lands on the section rather than on a full-height menu.

   This runs after the markup is parsed. If the script never loads, the element
   stays open and the nav degrades to the previous (working, if tall) layout —
   a visible menu is a safer failure than a hidden one.
   --------------------------------------------------------------------------- */
(function () {
  var nav = document.querySelector('.nav-collapse');
  if (!nav) return;
  var narrow = window.matchMedia('(max-width: 720px)');

  function sync(e) {
    // Only force a state when crossing the breakpoint, so a reader who opened
    // the menu deliberately is not overridden while they are using it.
    nav.open = !(e.matches);
  }
  sync(narrow);
  if (narrow.addEventListener) narrow.addEventListener('change', sync);
  else if (narrow.addListener) narrow.addListener(sync);

  nav.addEventListener('click', function (ev) {
    var a = ev.target.closest && ev.target.closest('a');
    if (a && narrow.matches) nav.open = false;
  });
})();
