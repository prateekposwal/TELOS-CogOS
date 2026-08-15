// TELOS Dashboard — chapter scrollspy + mini-nav (Item 8, 2026-08-15)
// ────────────────────────────────────────────────────────────────────────────
// The fixed right rail (#mini-nav) lists the nine story stops (chapters
// 01–08 + the deep dive). This module:
//
//   * Highlights the CURRENT chapter while scrolling: an IntersectionObserver
//     over the chapter sections with a band rootMargin, and on every boundary
//     crossing the section containing the band's top edge is recomputed from
//     real geometry (the "first section at the top of the band" rule). The
//     active link carries aria-current="true" + .active (a11y + visual).
//   * Click-to-scroll is NATIVE anchor navigation (href="#chapter-05"): no
//     JS hijacking, works without this script, scroll-margin-top clears the
//     sticky topbar; html{scroll-behavior:smooth} animates and the
//     prefers-reduced-motion block falls back to instant jumps (CSS-owned).
//   * No IntersectionObserver → the first chapter is pre-marked active and
//     click-to-scroll still works (anchor behavior is independent).
//
// Debug surface for the browser probe (measured, never invented):
//   window.__scrollspy = { active: () => data-chapter of the current stop }

(function () {
  'use strict';

  var links = Array.prototype.slice.call(document.querySelectorAll('#mini-nav .mini-nav-link'));
  var stops = [];
  for (var i = 0; i < links.length; i++) {
    var href = links[i].getAttribute('href');
    if (!href || href.charAt(0) !== '#') continue;
    var section = document.getElementById(href.slice(1));
    if (section) stops.push({ link: links[i], section: section, chapter: section.getAttribute('data-chapter') });
  }
  if (!stops.length) return;

  function setActive(chapter) {
    for (var i = 0; i < stops.length; i++) {
      var isCurrent = stops[i].chapter === chapter;
      if (isCurrent !== (stops[i].link.getAttribute('aria-current') === 'true')) {
        if (isCurrent) stops[i].link.setAttribute('aria-current', 'true');
        else stops[i].link.removeAttribute('aria-current');
        stops[i].link.classList.toggle('active', isCurrent);
      }
    }
    window.__scrollspy = {
      active: function () { return chapter; },
    };
  }

  // "Current" = the section whose box contains the band's top edge.
  function currentChapter(bandTopPx) {
    var found = null;
    for (var i = 0; i < stops.length; i++) {
      var r = stops[i].section.getBoundingClientRect();
      if (r.top <= bandTopPx && r.bottom > bandTopPx) found = stops[i].chapter;
    }
    return found;
  }

  var lastChapter = null;
  function refresh() {
    var bandTop = window.innerHeight * 0.3;   // matches the observer rootMargin
    var ch = currentChapter(bandTop);
    if (!ch) ch = lastChapter;                // in a gap → keep the last stop
    if (ch && ch !== lastChapter) { lastChapter = ch; setActive(ch); }
  }

  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(refresh, { rootMargin: '-30% 0px -60% 0px', threshold: 0 });
    for (var j = 0; j < stops.length; j++) io.observe(stops[j].section);
  } else {
    setActive(stops[0].chapter);  // honest default: the hero/first chapter
  }

  // Refresh once after load (layout settles) and on resize.
  refresh();
  window.addEventListener('resize', refresh);
})();
