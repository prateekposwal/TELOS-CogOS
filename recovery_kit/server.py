"""Localhost web UI for recovery_kit — run and test the toolkit from a browser.

STDLIB ONLY: http.server.ThreadingHTTPServer + argparse. Bound to 127.0.0.1
ONLY (never exposed to the network); default port 8766 — 8765 is the TELOS
dashboard.

TRANSPORT, NOT MATH (Lambda-2.3 honesty): every endpoint delegates to the
existing modules verbatim —

    space.estimate / space.verdict / space.fee_viability   (/api/estimate-space)
    benchmark.benchmark / benchmark.compare_to_presets     (/api/benchmark)
    triage.triage_case                                     (/api/triage)

The one exception is the intake gate checklist: intake.run_intake is an
interactive input() loop and cannot run inside an HTTP handler, so
/api/intake-gate assembles the SAME record schema from the canonical
GATE_ITEMS / DISQUALIFIERS constants and applies the SAME gate rule quoted
verbatim from run_intake (all(gate.values()) and not disqualifiers).
No key material ever passes through this server — same contract as the CLI.

Usage:
    PYTHONPATH=. python3 -m recovery_kit.server --port 8766

Then open http://127.0.0.1:8766/ (localhost only).
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import math
import os
import tempfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import benchmark as bench
from . import triage as triage_mod
from . import wallet_inspect
from .intake import DISQUALIFIERS, GATE_ITEMS
from .space import THROUGHPUT_PRESETS, estimate, fee_viability, verdict

logger = logging.getLogger("recovery_kit.server")

BIND_HOST = "127.0.0.1"      # localhost ONLY, by design — do not loosen
DEFAULT_PORT = 8766          # 8765 = TELOS dashboard
MAX_BODY_BYTES = 1_000_000   # request-size cap; these payloads are tiny
MAX_GEN_SAMPLES = 4000       # keeps /api/benchmark sub-second (spec cap)
MAX_KDF_SAMPLES = 24
DEFAULT_PRESET = "gpu-flagship"   # mirrors cli.py --throughput-preset default
# Fact keys mirror intake.run_intake's [fact] prompt order exactly.
FACT_KEYS = ("contact", "jurisdiction", "wallet_type", "has_wallet_file",
             "seed_words_remembered", "words_total", "passphrase_hints",
             "value_usd_estimate", "hardware_or_software")


def _json_safe(obj):
    """inf/nan -> None so strict JSON clients never see Infinity/NaN."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def api_health(payload):
    return {"ok": True}


def api_estimate_space(p):
    """Delegate to space.estimate + verdict (+ optional fee_viability)."""
    slots_in = p.get("slots")
    if not isinstance(slots_in, list) or not slots_in \
            or not all(isinstance(s, str) for s in slots_in):
        raise ValueError("slots must be a non-empty list of strings "
                         "(one slot per word: literal | ? | prefix:xyz | alt:a|b|c)")
    slots = [s.strip() for s in slots_in]
    if not all(slots):
        raise ValueError("slots contains a blank entry")
    try:
        unknown_order = int(p.get("unknown_order") or 0)
        if unknown_order < 0:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("unknown_order must be a non-negative integer")

    preset = p.get("throughput_preset", DEFAULT_PRESET)
    if preset not in THROUGHPUT_PRESETS:
        raise ValueError("throughput_preset must be one of %s"
                         % sorted(THROUGHPUT_PRESETS))
    # Mirror cli.main exactly: explicit throughput wins over preset (`or`).
    thr_override = p.get("throughput")
    try:
        throughput = float(thr_override) if thr_override else THROUGHPUT_PRESETS[preset]
    except (TypeError, ValueError):
        raise ValueError("throughput must be a number (seeds/sec)")

    usd_per_gpuhr = p.get("usd_per_gpuhr", 0.40)          # cli default
    res = estimate(slots, unknown_order, throughput, usd_per_gpuhr)
    out = {"estimate": _json_safe(res), "verdict": verdict(res)}

    value_usd = p.get("value_usd")
    if value_usd is not None:
        fee_rate = p.get("fee_rate", 0.10)                # cli default
        prob = p.get("assumed_success_prob")
        if prob is None:                                  # cli.main heuristic
            prob = 0.5 if res["valid_mnemonics_est"] < 1e9 else 0.15
        out["fee_viability"] = _json_safe(
            fee_viability(res, value_usd, fee_rate, prob))
    return out


def api_benchmark(p):
    """Measure local throughput via benchmark.benchmark, clamped for speed."""
    n_words = p.get("n_words", 12)
    try:
        n_words = int(n_words)
    except (TypeError, ValueError):
        raise ValueError("n_words must be an integer")
    if n_words not in bench.ENTROPY_BYTES:
        raise ValueError("n_words must be one of %s" % sorted(bench.ENTROPY_BYTES))

    def clamp(name, hi):
        raw = p.get(name, hi)
        try:
            v = int(raw)
        except (TypeError, ValueError):
            raise ValueError("%s must be an integer" % name)
        return max(1, min(hi, v)), v

    gen, gen_req = clamp("gen_samples", MAX_GEN_SAMPLES)
    kdf, kdf_req = clamp("kdf_samples", MAX_KDF_SAMPLES)

    report = bench.benchmark(n_words=n_words, gen_samples=gen,
                             pbkdf2_samples=kdf)
    return {
        "clamped_to": {"gen_samples": gen, "kdf_samples": kdf},
        "requested": {"gen_samples": gen_req, "kdf_samples": kdf_req},
        "limits": {"gen_samples_max": MAX_GEN_SAMPLES,
                   "kdf_samples_max": MAX_KDF_SAMPLES},
        "report": _json_safe(report),
        "presets_vs_measured": bench.compare_to_presets(report),
    }


def api_intake_gate(p):
    """Ownership-gate checklist runner (non-interactive form of run_intake).

    run_intake itself is input()-driven and cannot execute inside an HTTP
    handler, so this builds the identical record schema from the canonical
    GATE_ITEMS / DISQUALIFIERS constants and applies the gate rule quoted
    VERBATIM from intake.run_intake:
        rec["gate_cleared"] = all(rec["gate"].values()) and not rec["disqualifiers"]
    """
    case_id = str(p.get("case_id") or "").strip()
    if not case_id:
        raise ValueError("case_id is required")
    if any(c in case_id for c in "/\\") or case_id in (".", ".."):
        raise ValueError("case_id must not contain path separators")

    gate_in = p.get("gate")
    if gate_in is None:
        gate_in = {}
    if not isinstance(gate_in, dict):
        raise ValueError("gate must be an object of item -> bool")
    unknown_gate = sorted(k for k in gate_in if k not in GATE_ITEMS)
    if unknown_gate:
        raise ValueError("unknown gate items %s; valid: %s"
                         % (unknown_gate, list(GATE_ITEMS)))
    gate = {k: bool(gate_in.get(k, False)) for k in GATE_ITEMS}

    dq_in = p.get("disqualifiers")
    if dq_in is None:
        dq_in = []
    if not isinstance(dq_in, list) or not all(isinstance(k, str) for k in dq_in):
        raise ValueError("disqualifiers must be a list of red-flag keys")
    bad_dq = sorted(k for k in dq_in if k not in DISQUALIFIERS)
    if bad_dq:
        raise ValueError("unknown disqualifiers %s; valid: %s"
                         % (bad_dq, list(DISQUALIFIERS)))
    disqualifiers = [k for k in DISQUALIFIERS if k in set(dq_in)]  # canonical order

    facts_in = p.get("case_facts")
    if facts_in is None:
        facts_in = {}
    if not isinstance(facts_in, dict):
        raise ValueError("case_facts must be an object of fact -> string")
    case_facts = {k: "" if facts_in.get(k) is None else str(facts_in.get(k))
                  for k in FACT_KEYS}

    rec = {"case_id": case_id,
           "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "gate": gate, "disqualifiers": disqualifiers,
           "case_facts": case_facts}
    # Gate rule — verbatim from intake.run_intake (see docstring).
    rec["gate_cleared"] = all(rec["gate"].values()) and not rec["disqualifiers"]
    return {"record": rec,
            "gate_status": "CLEARED" if rec["gate_cleared"] else "BLOCKED",
            "next_step": ("paste this record into the Triage form"
                          if rec["gate_cleared"]
                          else "clear every gate item with zero red flags first")}


def api_triage(p):
    """Paste-intake-JSON -> triage.triage_case (via an ephemeral temp file).

    triage_case takes a PATH, so the pasted record is written to a private
    temp file that is deleted immediately afterwards. triage_case enforces
    the gate itself: records without gate_cleared=True come back BLOCKED.
    """
    rec = p.get("intake") if isinstance(p.get("intake"), dict) else p
    if not isinstance(rec, dict):
        raise ValueError("body must be an intake record object (paste intake.json)")
    fd, tmp_name = tempfile.mkstemp(suffix=".json", prefix="rk_triage_")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(rec, f)
        result = triage_mod.triage_case(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return _json_safe(result)


def api_wallet_inspect(p):
    """Upload an ENCRYPTED wallet artifact -> in-memory format identification.

    Bytes are analyzed in memory ONLY, never written to disk or logged, and
    discarded before the response is sent. Handles raw body upload
    (Content-Type not required to be JSON) via the special transport field.
    """
    data = p.get("_file_bytes")
    if data is None:
        raise ValueError("wallet file bytes required "
                         "(upload via multipart or raw body)")
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("_file_bytes must be bytes")
    filename = str(p.get("_filename") or "uploaded_wallet")
    report = wallet_inspect.inspect_wallet_file(bytes(data), filename)
    return {"report": _json_safe(report),
            "warning": ("analyzed in memory only; bytes discarded after response. "
                        "NEVER upload unencrypted seeds/keys — keep those local.")}


POST_ROUTES = {
    "/api/estimate-space": api_estimate_space,
    "/api/benchmark": api_benchmark,
    "/api/intake-gate": api_intake_gate,
    "/api/triage": api_triage,
    "/api/wallet-inspect": api_wallet_inspect,
}


# ─── Single-page UI (embedded; no external assets, no CDN) ───────────────────

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>recovery_kit — local operator console</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         margin: 0 auto; max-width: 980px; padding: 1rem 1.25rem 4rem;
         line-height: 1.45; }
  h1 { font-size: 1.35rem; margin: 0.2rem 0 0.3rem; }
  h2 { font-size: 1.05rem; margin: 0 0 0.5rem; border-bottom: 1px solid #8884;
       padding-bottom: 0.25rem; }
  .banner { background: #b3541e; color: #fff; font-weight: 600;
            padding: 0.6rem 0.8rem; border-radius: 6px; margin: 0.6rem 0 1.2rem; }
  section { border: 1px solid #8884; border-radius: 8px; padding: 0.9rem 1rem;
            margin-bottom: 1.2rem; background: #8881; }
  label { display: block; margin: 0.45rem 0 0.12rem; font-size: 0.86rem; }
  label.check { display: flex; gap: 0.45rem; align-items: baseline;
                margin: 0.22rem 0; cursor: pointer; font-size: 0.82rem; }
  textarea, input[type=text], input[type=number] {
    width: 100%; padding: 0.35rem 0.45rem; border: 1px solid #8888;
    border-radius: 5px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.85rem; background: inherit; color: inherit; }
  select { padding: 0.3rem; border-radius: 5px; border: 1px solid #8888;
           background: inherit; color: inherit; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 0 0.8rem; }
  fieldset { border: 1px dashed #8886; border-radius: 6px; margin: 0.6rem 0;
             padding: 0.4rem 0.7rem 0.6rem; }
  legend { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;
           opacity: 0.75; padding: 0 0.3rem; }
  button { margin-top: 0.7rem; padding: 0.45rem 1.1rem; font-size: 0.9rem;
           cursor: pointer; border-radius: 6px; border: 1px solid #8888;
           background: #2a6fdb; color: #fff; }
  button:hover { filter: brightness(1.1); }
  pre.out { background: #0002; border: 1px solid #8884; border-radius: 6px;
            padding: 0.6rem 0.7rem; min-height: 1.2rem; white-space: pre-wrap;
            word-break: break-word; font-size: 0.78rem; max-height: 26rem;
            overflow: auto; }
  code { font-size: 0.82em; }
  .note { font-size: 0.78rem; opacity: 0.85; margin-top: 0.35rem; }
</style>
</head>
<body>
<h1>recovery_kit — local operator console</h1>
<div class="banner">&#9888;&#65039; Local tool. Ownership gate must clear before any attempt plan.</div>
<p class="note"><a href="/">Tools</a> &middot; <a href="/wallet">Wallet file inspection</a></p>

<section>
  <h2>1 &middot; Estimate search space <code>space.estimate</code></h2>
  <form id="f-estimate" data-endpoint="/api/estimate-space" data-builder="estimate" data-out="estimate-out">
    <label for="slots">Slots — one per line (DSL: <code>word</code> literal &middot;
      <code>?</code> any &middot; <code>prefix:xyz</code> &middot; <code>alt:a|b|c</code>)</label>
    <textarea id="slots" name="slots" rows="7"
      placeholder="abandon&#10;?&#10;prefix:elep&#10;alt:snow|salt&#10;?&#10;?&#10;?&#10;?&#10;?&#10;?&#10;?&#10;?"></textarea>
    <div class="grid">
      <div><label for="unknown_order">Unknown-order words (&times;k!)</label>
        <input type="number" id="unknown_order" name="unknown_order" min="0" step="1" value="0"></div>
      <div><label for="throughput_preset">Throughput preset (conservative placeholder)</label>
        <select id="throughput_preset" name="throughput_preset">__PRESET_OPTIONS__</select></div>
      <div><label for="throughput">Throughput override (seeds/s, optional)</label>
        <input type="number" id="throughput" name="throughput" min="0" step="any"></div>
      <div><label for="usd_per_gpuhr">USD per GPU-hour</label>
        <input type="number" id="usd_per_gpuhr" name="usd_per_gpuhr" min="0" step="any" value="0.40"></div>
      <div><label for="value_usd">Wallet value USD (optional &rarr; fee viability)</label>
        <input type="number" id="value_usd" name="value_usd" min="0" step="any"></div>
      <div><label for="fee_rate">Fee rate (default 0.10)</label>
        <input type="number" id="fee_rate" name="fee_rate" min="0" max="1" step="any" value="0.10"></div>
      <div><label for="assumed_success_prob">Assumed success probability (optional)</label>
        <input type="number" id="assumed_success_prob" name="assumed_success_prob" min="0" max="1" step="any"></div>
    </div>
    <button type="submit">Estimate space</button>
    <p class="note">Checksum divisor is an expected-value filter — treat big spaces as
      order-of-magnitude; benchmark on the real attempt host before quoting.</p>
  </form>
  <pre class="out" id="estimate-out">(results appear here)</pre>
</section>

<section>
  <h2>2 &middot; Throughput benchmark <code>benchmark.benchmark</code></h2>
  <form id="f-bench" data-endpoint="/api/benchmark" data-builder="benchmark" data-out="bench-out">
    <div class="grid">
      <div><label for="n_words">Phrase length (words)</label>
        <select id="n_words" name="n_words">__N_WORDS_OPTIONS__</select></div>
      <div><label for="gen_samples">Generation samples (max 4000)</label>
        <input type="number" id="gen_samples" name="gen_samples" min="1" max="4000" step="1" value="4000"></div>
      <div><label for="kdf_samples">PBKDF2 samples (max 24)</label>
        <input type="number" id="kdf_samples" name="kdf_samples" min="1" max="24" step="1" value="24"></div>
    </div>
    <button type="submit">Benchmark this host</button>
    <p class="note">Synthetic, non-secret targets only. Samples are clamped server-side
      so requests stay fast; quotes start from MEASURED numbers (Lambda-2.3).</p>
  </form>
  <pre class="out" id="bench-out">(results appear here)</pre>
</section>

<section>
  <h2>3 &middot; Intake ownership gate <code>intake.GATE_ITEMS</code> / <code>DISQUALIFIERS</code></h2>
  <form id="f-intake" data-endpoint="/api/intake-gate" data-builder="intake" data-out="intake-out">
    <div class="grid"><div><label for="case_id">Case ID</label>
      <input type="text" id="case_id" name="case_id" placeholder="CASE-001"></div></div>
    <fieldset><legend>Gate items — every one must verify TRUE</legend>
__GATE_ROWS__
    </fieldset>
    <fieldset><legend>Red flags — any one present blocks the gate</legend>
__DQ_ROWS__
    </fieldset>
    <fieldset><legend>Case facts</legend>
      <div class="grid">
__FACT_INPUTS__
      </div>
    </fieldset>
    <button type="submit">Evaluate gate</button>
    <p class="note">Mirrors intake.run_intake's record + gate rule without the interactive
      prompts. The operator still verifies every attestation live on a recorded
      screen-share. CLEARED output can be pasted straight into the Triage form below.</p>
  </form>
  <pre class="out" id="intake-out">(results appear here)</pre>
</section>

<section>
  <h2>4 &middot; Triage intake record <code>triage.triage_case</code></h2>
  <form id="f-triage" data-endpoint="/api/triage" data-builder="triage" data-out="triage-out">
    <label for="intake_json">Intake record JSON (paste <code>cases/&lt;id&gt;/intake.json</code>
      or the CLEARED output from section 3)</label>
    <textarea id="intake_json" name="intake_json" rows="10"
      placeholder='{"case_id": "CASE-001", "created_utc": "...", "gate": {"identity_verified": true}, "disqualifiers": [], "case_facts": {}, "gate_cleared": true}'></textarea>
    <button type="submit">Triage case</button>
    <p class="note">Records without <code>gate_cleared: true</code> come back BLOCKED —
      triage.py refuses to classify them. No attempt plan exists until the gate clears.</p>
  </form>
  <pre class="out" id="triage-out">(results appear here)</pre>
</section>

<p class="note">All computation delegates to the recovery_kit modules on this host —
  the server is transport only. Estimates are order-of-magnitude; throughput presets are
  placeholders until benchmarked on the actual attempt host; generated plans carry
  TODO(verify) markers. Bound to 127.0.0.1 only; nothing leaves this machine.</p>

<script>
"use strict";
var FACT_KEY_LIST = __FACT_KEYS_JSON__;

function numOrNull(v) {
  var s = String(v === null || v === undefined ? "" : v).trim();
  return s === "" ? null : Number(s);
}

var BUILDERS = {
  estimate: function (form) {
    var slots = String(form.elements["slots"].value || "")
      .split("\n").map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length > 0; });
    if (slots.length === 0) throw new Error("enter at least one slot");
    var payload = {
      slots: slots,
      unknown_order: Math.max(0, Math.floor(numOrNull(form.elements["unknown_order"].value) || 0)),
      throughput_preset: form.elements["throughput_preset"].value,
      usd_per_gpuhr: numOrNull(form.elements["usd_per_gpuhr"].value)
    };
    if (payload.usd_per_gpuhr === null) payload.usd_per_gpuhr = 0.40;
    var thr = numOrNull(form.elements["throughput"].value);
    if (thr !== null) payload.throughput = thr;
    ["value_usd", "fee_rate", "assumed_success_prob"].forEach(function (key) {
      var v = numOrNull(form.elements[key].value);
      if (v !== null) payload[key] = v;
    });
    return payload;
  },
  benchmark: function (form) {
    return {
      n_words: Number(form.elements["n_words"].value),
      gen_samples: numOrNull(form.elements["gen_samples"].value),
      kdf_samples: numOrNull(form.elements["kdf_samples"].value)
    };
  },
  intake: function (form) {
    var caseId = String(form.elements["case_id"].value || "").trim();
    if (!caseId) throw new Error("case_id is required");
    var gate = {};
    form.querySelectorAll('input[type="checkbox"][data-kind="gate"]').forEach(function (cb) {
      gate[cb.name] = cb.checked;
    });
    var dq = [];
    form.querySelectorAll('input[type="checkbox"][data-kind="dq"]').forEach(function (cb) {
      if (cb.checked) dq.push(cb.name);
    });
    var facts = {};
    FACT_KEY_LIST.forEach(function (k) {
      var el = form.elements[k];
      facts[k] = el ? String(el.value).trim() : "";
    });
    return { case_id: caseId, gate: gate, disqualifiers: dq, case_facts: facts };
  },
  triage: function (form) {
    var raw = String(form.elements["intake_json"].value || "").trim();
    if (!raw) throw new Error("paste an intake record JSON first");
    return JSON.parse(raw);   // parse errors surface as client errors below
  }
};

document.querySelectorAll("form[data-endpoint]").forEach(function (form) {
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var out = document.getElementById(form.getAttribute("data-out"));
    var payload;
    try {
      payload = BUILDERS[form.getAttribute("data-builder")](form);
    } catch (err) {
      out.textContent = "client error: " + err.message;
      return;
    }
    out.textContent = "working...";
    fetch(form.getAttribute("data-endpoint"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (resp) {
      return resp.json().then(function (data) {
        out.textContent = "HTTP " + resp.status + "\n\n" + JSON.stringify(data, null, 2);
      });
    }).catch(function (err) {
      out.textContent = "request failed: " + err.message;
    });
  });
});
</script>
</body>
</html>
"""


def _build_page() -> str:
    """Fill template tokens from the real module constants (single source)."""
    preset_options = "".join(
        '<option value="%s"%s>%s (%s seeds/s)</option>'
        % (name, " selected" if name == DEFAULT_PRESET else "",
           name, format(val, ",.0f"))
        for name, val in sorted(THROUGHPUT_PRESETS.items()))
    n_words_options = "".join(
        '<option value="%d"%d>%d words</option>'
        % (n, 1 if n == 12 else 0, n)
        for n in sorted(bench.ENTROPY_BYTES))
    gate_rows = "".join(
        '<label class="check"><input type="checkbox" data-kind="gate" name="%s">'
        '<span><code>%s</code> — %s</span></label>\n'
        % (k, k, html.escape(desc)) for k, desc in GATE_ITEMS.items())
    dq_rows = "".join(
        '<label class="check"><input type="checkbox" data-kind="dq" name="%s">'
        '<span><code>%s</code> — %s</span></label>\n'
        % (k, k, html.escape(desc)) for k, desc in DISQUALIFIERS.items())
    fact_inputs = "".join(
        '<div><label for="fact_%s">%s</label>'
        '<input type="text" id="fact_%s" name="%s"></div>\n'
        % (k, k, k, k) for k in FACT_KEYS)
    return (_PAGE_TEMPLATE
            .replace("__PRESET_OPTIONS__", preset_options)
            .replace("__N_WORDS_OPTIONS__", n_words_options)
            .replace("__GATE_ROWS__", gate_rows)
            .replace("__DQ_ROWS__", dq_rows)
            .replace("__FACT_INPUTS__", fact_inputs)
            .replace("__FACT_KEYS_JSON__", json.dumps(list(FACT_KEYS))))


PAGE = _build_page()


# ─── Wallet file inspection page (Class C) ────────────────────────────────────

_WALLET_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>recovery_kit — wallet file inspection</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         margin: 0 auto; max-width: 760px; padding: 1rem 1.25rem 4rem; line-height: 1.45; }
  h1 { font-size: 1.35rem; margin: 0.2rem 0 0.3rem; }
  .banner { background: #b3541e; color: #fff; font-weight: 600; padding: 0.6rem 0.8rem;
            border-radius: 6px; margin: 0.6rem 0 1.2rem; }
  .danger { background: #8b1a1a; }
  section { border: 1px solid #8884; border-radius: 8px; padding: 0.9rem 1rem; background: #8881; }
  button { margin-top: 0.7rem; padding: 0.45rem 1.1rem; font-size: 0.9rem; cursor: pointer;
           border-radius: 6px; border: 1px solid #8888; background: #2a6fdb; color: #fff; }
  pre.out { background: #0002; border: 1px solid #8884; border-radius: 6px; padding: 0.6rem 0.7rem;
            white-space: pre-wrap; word-break: break-word; font-size: 0.8rem; max-height: 24rem;
            overflow: auto; }
  .note { font-size: 0.78rem; opacity: 0.85; margin-top: 0.35rem; }
  code { font-size: 0.82em; }
</style>
</head>
<body>
<h1>recovery_kit — wallet file inspection</h1>
<div class="banner">&#9888;&#65039; Local tool. Ownership gate must clear before any attempt plan.</div>
<div class="banner danger">&#128274; ENCRYPTED ARTIFACTS ONLY. NEVER type or paste seed words,
  passphrases, or private keys into any browser page. File bytes are analyzed in memory and
  discarded — nothing is stored or logged.</div>

<section>
  <h2>Upload an encrypted wallet file for format identification</h2>
  <form id="f-wallet">
    <input type="file" id="file" name="file" accept=".dat,.wallet,.json,.tar,.gz,application/octet-stream">
    <button type="submit">Inspect in memory</button>
  </form>
  <p class="note">Supports: Bitcoin Core <code>wallet.dat</code> (BerkeleyDB), Multibit
    <code>.wallet</code>, Electrum files, Android bitcoin-wallet backups, unknown binary.
    Detects format family + whether it looks encrypted; recommends the Class C plan.</p>
  <pre class="out" id="wallet-out">(upload a file — report appears here)</pre>
</section>

<p class="note"><a href="/">&larr; back to tools</a> &middot; Bound to 127.0.0.1 only; nothing leaves this machine.</p>

<script>
"use strict";
document.getElementById("f-wallet").addEventListener("submit", function (ev) {
  ev.preventDefault();
  var out = document.getElementById("wallet-out");
  var input = document.getElementById("file");
  var file = input.files && input.files[0];
  if (!file) { out.textContent = "client error: choose a file first"; return; }
  out.textContent = "working (in memory only)...";
  fetch("/api/wallet-inspect", {
    method: "POST",
    headers: { "X-Filename": file.name },
    body: file
  }).then(function (r) { return r.json(); }).then(function (data) {
    out.textContent = "HTTP " + (data.error ? "400" : "200") + "\n\n" +
      JSON.stringify(data, null, 2);
  }).catch(function (err) { out.textContent = "request failed: " + err.message; });
});
</script>
</body>
</html>
"""


# ─── HTTP handler ─────────────────────────────────────────────────────────────

class RecoveryKitHandler(BaseHTTPRequestHandler):
    server_version = "recovery_kit_server/1.0"

    def _send_json(self, obj, status: int = 200):
        body = json.dumps(_json_safe(obj), indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("", "/"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/wallet":
            body = _WALLET_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/health":
            self._send_json(api_health({}))
            return
        self._send_json({"error": "not found: %s" % path}, status=404)

    def do_POST(self):
        path = urlparse(self.path).path
        fn = POST_ROUTES.get(path)
        if fn is None:
            self._send_json({"error": "not found: %s" % path}, status=404)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json({"error": "invalid Content-Length"}, status=400)
            return
        # Wallet inspection accepts a RAW binary upload (encrypted artifact);
        # it never arrives as JSON. Everything else stays JSON-only.
        if path == "/api/wallet-inspect":
            if length > wallet_inspect.MAX_INSPECT_BYTES:
                self._send_json({"error": "body too large (max %d bytes)"
                                         % wallet_inspect.MAX_INSPECT_BYTES},
                                status=413)
                return
            raw = self.rfile.read(length) if length > 0 else b""
            if not raw:
                self._send_json({"error": "empty upload"}, status=400)
                return
            ctype = self.headers.get("Content-Type") or ""
            filename = ""
            if "filename=" in ctype:      # multipart form; pull the filename
                import re
                m = re.search(r'filename="([^"]*)"', ctype)
                if m:
                    filename = m.group(1)
            elif self.headers.get("X-Filename"):
                filename = self.headers["X-Filename"]
            try:
                self._send_json(api_wallet_inspect({"_file_bytes": raw,
                                                    "_filename": filename}))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
            except Exception as exc:
                logger.exception("handler failed for %s", path)
                self._send_json({"error": "%s: %s" % (type(exc).__name__, exc)},
                                status=500)
            return
        if length > MAX_BODY_BYTES:
            self._send_json({"error": "body too large (max %d bytes)" % MAX_BODY_BYTES},
                            status=413)
            return
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, ValueError) as exc:
            self._send_json({"error": "invalid JSON body: %s" % exc}, status=400)
            return
        if not isinstance(payload, dict):
            self._send_json({"error": "JSON body must be an object"}, status=400)
            return
        try:
            self._send_json(fn(payload))
        except ValueError as exc:            # bad input -> honest 400
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:             # logged, never swallowed (Lambda-2.3)
            logger.exception("handler failed for %s", path)
            self._send_json({"error": "%s: %s" % (type(exc).__name__, exc)}, status=500)

    def log_message(self, fmt, *args):       # quiet unless debugging
        logger.debug("%s %s", self.address_string(), fmt % args)


def create_server(host: str = BIND_HOST, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    """Bind the UI server. host is 127.0.0.1 by construction — localhost only."""
    return ThreadingHTTPServer((host, port), RecoveryKitHandler)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="recovery_kit local web UI (binds 127.0.0.1 ONLY; "
                    "default port %d — 8765 is the TELOS dashboard)" % DEFAULT_PORT)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help="port to listen on (default %(default)s)")
    args = ap.parse_args(argv)
    httpd = create_server(port=args.port)
    bind_host, bind_port = httpd.server_address[0], httpd.server_address[1]
    print("recovery_kit local UI  ->  http://%s:%d/  (bound to %s ONLY; Ctrl-C to stop)"
          % (bind_host, bind_port, bind_host))
    print("Local tool. Ownership gate must clear before any attempt plan.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
