// TELOS Dashboard — lazy three.js loader (Item 6b, 2026-08-15)
// ────────────────────────────────────────────────────────────────────────────
// three.min.js (~600 KB) + OrbitControls.js are ONLY used by chapter 05
// (the 3D Memory Nebula, #kg-panel-bubble). Loading them eagerly on every
// page open is the single largest wasted-payload item of the dashboard.
// This loader defers the whole vendor chain until the nebula chapter
// actually approaches the viewport:
//
//   * IntersectionObserver on the chapter-05 panel with a 900px preload
//     margin — the scripts start downloading BEFORE the canvas scrolls on
//     screen ("near chapter 05" is a deliberate head-start, not a
//     last-moment stall; scrolling past chapter 04 is enough).
//   * Strict order preserved: three.min.js → OrbitControls.js →
//     knowledge-3d.js (chained onload + non-async injection, so the
//     OrbitControls UMD guard never sees a missing THREE and the 3D module
//     always parses after its dependencies).
//   * Failure is honest: if three.min.js errors, OrbitControls is skipped
//     (its own guard warns) and knowledge-3d.js still loads — its
//     `typeof THREE === 'undefined'` gate keeps the 2D nebula fallback
//     alive. Never a silent swallow (Λ2.3).
//   * One-shot: after the chain starts, the observer is disconnected —
//     re-visits never re-inject duplicate scripts.
//   * No IntersectionObserver? Fall back to a deferred immediate load —
//     the 3D still works, just without the lazy win.
//
// Debug surface for the browser probe (measured, never invented):
//   window.__kg3dLazy = { state: 'idle'|'loading'|'loaded'|'error',
//                          scripts: [src, ...], timing: ms }

(function () {
  'use strict';

  var CHAIN = [
    'dashboard/vendor/three.min.js',
    'dashboard/vendor/OrbitControls.js',
    'dashboard/js/knowledge-3d.js'
  ];

  var state = 'idle';        // idle → loading → loaded | error
  var started = false;
  var loadedScripts = [];
  var startAt = 0;

  // Initial handle is honest from parse time (probe reads 'idle' before
  // any interaction — proves three.js is NOT blocking initial load).
  window.__kg3dLazy = { state: 'idle', scripts: [], timing: 0 };

  function mark(s) {
    state = s;
    window.__kg3dLazy = {
      state: state,
      scripts: loadedScripts.slice(),
      timing: startAt ? Math.round(performance.now() - startAt) : 0,
    };
  }

  function inject(src, onload, onerror) {
    var s = document.createElement('script');
    s.src = src;
    // Keep classic-script ordering deterministic (no async reordering).
    s.async = false;
    s.onload = function () {
      loadedScripts.push(src);
      if (onload) onload();
    };
    s.onerror = function () {
      if (onerror) onerror(src);
    };
    (document.head || document.documentElement).appendChild(s);
  }

  function runChain() {
    if (started) return;
    started = true;
    startAt = performance.now();
    state = 'loading';
    mark('loading');
    inject(CHAIN[0], function () {
      inject(CHAIN[1], function () {
        inject(CHAIN[2], function () {
          mark('loaded');
        }, function () {
          // knowledge-3d.js failed: its 2D fallback never gets a chance,
          // but the failure is loud and the 2D nebula (knowledge-graph.js)
          // still paints the canvas. Kintsugi: recorded, not swallowed.
          console.warn('[lazy-3d] knowledge-3d.js failed to load — 2D nebula stays.');
          mark('error');
        });
      }, function () {
        // OrbitControls failed: skip it (its own guard warns), but the 3D
        // module still needs THREE — keep going; knowledge-3d.js bails to
        // the 2D fallback if THREE is missing. Never block the page.
        console.warn('[lazy-3d] OrbitControls.js failed to load — skipping.');
        inject(CHAIN[2], function () { mark('loaded'); }, function () {
          console.warn('[lazy-3d] knowledge-3d.js failed to load — 2D nebula stays.');
          mark('error');
        });
      });
    }, function () {
      // three.min.js failed: skip the whole chain; knowledge-3d.js would
      // only bail on the missing-THREE guard anyway. 2D nebula survives.
      console.warn('[lazy-3d] three.min.js failed to load — 3D Memory Nebula disabled, 2D fallback stays.');
      mark('error');
    });
  }

  var panel = document.getElementById('kg-panel-bubble');
  if (panel && 'IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      if (entries.some(function (en) { return en.isIntersecting; })) {
        io.disconnect();
        runChain();
      }
    }, { rootMargin: '900px 0px', threshold: 0 });
    io.observe(panel);
  } else {
    // No IO (ancient browser) or missing panel: deferred load, still not
    // blocking first paint (timeout keeps parse ahead of the 600KB fetch).
    setTimeout(runChain, 300);
  }
})();
