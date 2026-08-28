"""recovery_kit.server tests — ephemeral-port HTTP against the real modules.

Starts the server in-process on port 0 (OS-assigned), hits it with urllib,
and asserts /api/estimate-space output matches recovery_kit.space exactly
(the server must be transport, not new math). Fast: one deliberately small
benchmark call plus one clamped-to-the-cap call, everything else is pure math.
"""
import json
import threading
import urllib.error
import urllib.request

import pytest

from recovery_kit.commands import CLASS_B
from recovery_kit.intake import DISQUALIFIERS, GATE_ITEMS
from recovery_kit.server import (BIND_HOST, DEFAULT_PORT, create_server,
                                 MAX_GEN_SAMPLES, MAX_KDF_SAMPLES)
from recovery_kit.space import (THROUGHPUT_PRESETS, estimate, fee_viability,
                                verdict)


@pytest.fixture(scope="module")
def base_url():
    httpd = create_server(port=0)              # ephemeral port, in-process
    host, port = httpd.server_address[0], httpd.server_address[1]
    assert host == BIND_HOST == "127.0.0.1"    # loopback ONLY, never 0.0.0.0
    assert DEFAULT_PORT == 8766 and DEFAULT_PORT != 8765   # 8765 = TELOS dashboard
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % port
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.status, dict(resp.headers), resp.read().decode("utf-8")


def _post(base_url, path, payload):
    req = urllib.request.Request(
        base_url + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:      # error bodies are JSON too
        return exc.code, json.loads(exc.read().decode("utf-8"))


CLEARED_GATE = {k: True for k in GATE_ITEMS}


# ─── server basics ────────────────────────────────────────────────────────────

def test_health_ok(base_url):
    status, _, body = _get(base_url + "/api/health")
    assert status == 200
    assert json.loads(body) == {"ok": True}


def test_index_serves_honest_single_page(base_url):
    status, headers, body = _get(base_url + "/")
    assert status == 200
    assert headers.get("Content-Type", "").startswith("text/html")
    low = body.lower()
    # honest banner, verbatim
    assert "local tool. ownership gate must clear before any attempt plan." in low
    # all four forms wired to all four endpoints; results land in <pre> targets
    for endpoint in ("/api/estimate-space", "/api/benchmark",
                     "/api/intake-gate", "/api/triage"):
        assert endpoint in body
    for out_id in ("estimate-out", "bench-out", "intake-out", "triage-out"):
        assert 'id="%s"' % out_id in body
    # no external CDN/assets: nothing fetched over the network, no src= tags
    assert "https://" not in body and "src=" not in low


# ─── /api/estimate-space must match space.estimate EXACTLY ──────────────────

def test_estimate_space_matches_space_module_math(base_url):
    slots = ["abandon"] + ["?"] * 11
    payload = {"slots": slots, "unknown_order": 2,
               "usd_per_gpuhr": 0.40, "value_usd": 20000,
               "fee_rate": 0.10, "assumed_success_prob": 0.25}
    status, body = _post(base_url, "/api/estimate-space", payload)
    assert status == 200
    expected = estimate(slots, 2, THROUGHPUT_PRESETS["gpu-flagship"], 0.40)
    assert body["estimate"] == expected                 # identical dict
    assert body["verdict"] == verdict(expected)
    assert body["fee_viability"] == fee_viability(expected, 20000.0, 0.10, 0.25)


def test_estimate_space_throughput_override_wins_over_preset(base_url):
    slots = ["?"] * 12
    status, body = _post(base_url, "/api/estimate-space",
                         {"slots": slots, "throughput": 1234.5})
    assert status == 200
    assert body["estimate"] == estimate(slots, 0, 1234.5, 0.40)
    assert "fee_viability" not in body                  # no value_usd -> no section


def test_estimate_space_cli_default_success_prob_heuristic(base_url):
    # tiny space -> cli.main heuristic picks 0.5 when prob omitted
    slots = ["abandon"] * 12
    status, body = _post(base_url, "/api/estimate-space",
                         {"slots": slots, "throughput": 1e9, "value_usd": 10000})
    assert status == 200
    assert body["fee_viability"]["assumed_success_prob"] == 0.5


def test_estimate_space_rejects_bad_slot_word(base_url):
    status, body = _post(base_url, "/api/estimate-space",
                         {"slots": ["notaword"] + ["?"] * 11})
    assert status == 400
    assert "notaword" in body["error"]


def test_estimate_space_rejects_wrong_length_and_blank_slots(base_url):
    status, body = _post(base_url, "/api/estimate-space", {"slots": ["?", "?"]})
    assert status == 400 and "12/15/18/21/24" in body["error"]
    status, body = _post(base_url, "/api/estimate-space", {"slots": []})
    assert status == 400 and "slots" in body["error"]
    status, body = _post(base_url, "/api/estimate-space", {"slots": ["  "] + ["?"] * 11})
    assert status == 400


# ─── /api/benchmark delegates to benchmark.benchmark, clamped ───────────────

def test_benchmark_clamps_samples_and_returns_report(base_url):
    status, body = _post(base_url, "/api/benchmark",
                         {"n_words": 12, "gen_samples": 10 ** 9,
                          "kdf_samples": 9999})
    assert status == 200
    assert body["requested"] == {"gen_samples": 10 ** 9, "kdf_samples": 9999}
    assert body["clamped_to"] == {"gen_samples": MAX_GEN_SAMPLES,     # 4000
                                  "kdf_samples": MAX_KDF_SAMPLES}     # 24
    rep = body["report"]
    assert rep["n_words"] == 12 and rep["pbkdf2_rounds"] == 2048
    assert rep["effective_seeds_per_sec"] <= min(rep["gen_phrases_per_sec"],
                                                 rep["pbkdf2_per_sec"])
    assert rep["bottleneck"] in ("generation+checksum", "pbkdf2-2048")
    assert any("gpu-flagship" in line for line in body["presets_vs_measured"])


def test_benchmark_small_request_passes_through_unclamped(base_url):
    status, body = _post(base_url, "/api/benchmark",
                         {"n_words": 24, "gen_samples": 50, "kdf_samples": 2})
    assert status == 200
    assert body["clamped_to"] == {"gen_samples": 50, "kdf_samples": 2}
    assert body["report"]["n_words"] == 24


def test_benchmark_rejects_bad_n_words(base_url):
    status, body = _post(base_url, "/api/benchmark", {"n_words": 13})
    assert status == 400 and "n_words" in body["error"]


# ─── /api/intake-gate mirrors intake.run_intake's record + gate rule ────────

def test_intake_gate_cleared_matches_run_intake_record_schema(base_url):
    status, body = _post(base_url, "/api/intake-gate",
                         {"case_id": "CASE-WEB-1", "gate": CLEARED_GATE,
                          "disqualifiers": [],
                          "case_facts": {"seed_words_remembered": "3",
                                         "words_total": "12"}})
    assert status == 200 and body["gate_status"] == "CLEARED"
    rec = body["record"]
    # exact run_intake record schema
    assert set(rec) == {"case_id", "created_utc", "gate", "disqualifiers",
                        "case_facts", "gate_cleared"}
    assert set(rec["gate"]) == set(GATE_ITEMS)          # canonical items only
    assert rec["disqualifiers"] == []
    assert rec["gate_cleared"] is True
    assert rec["case_facts"]["seed_words_remembered"] == "3"


def test_intake_gate_blocks_on_uncleared_item_or_red_flag(base_url):
    partial = dict(CLEARED_GATE, engagement_signed=False)
    status, body = _post(base_url, "/api/intake-gate",
                         {"case_id": "CASE-WEB-2", "gate": partial})
    assert status == 200 and body["gate_status"] == "BLOCKED"
    assert body["record"]["gate_cleared"] is False

    status, body = _post(base_url, "/api/intake-gate",
                         {"case_id": "CASE-WEB-3", "gate": CLEARED_GATE,
                          "disqualifiers": ["third_party"]})
    assert body["record"]["disqualifiers"] == ["third_party"]       # canonical key
    assert body["gate_status"] == "BLOCKED"


def test_intake_gate_validates_keys_and_case_id(base_url):
    status, body = _post(base_url, "/api/intake-gate",
                         {"case_id": "X", "gate": {"made_up_item": True}})
    assert status == 400 and "made_up_item" in body["error"]
    status, body = _post(base_url, "/api/intake-gate",
                         {"case_id": "X", "gate": {},
                          "disqualifiers": ["made_up_flag"]})
    assert status == 400 and "made_up_flag" in body["error"]
    assert len(DISQUALIFIERS) >= 6                       # sanity on constants
    status, body = _post(base_url, "/api/intake-gate", {"case_id": ""})
    assert status == 400 and "case_id" in body["error"]
    status, body = _post(base_url, "/api/intake-gate", {"case_id": "../evil"})
    assert status == 400 and "path separators" in body["error"]


# ─── /api/triage delegates to triage.triage_case via temp file ──────────────

def test_triage_refuses_record_without_gate_cleared(base_url):
    record = {"case_id": "CASE-WEB-BLOCKED", "created_utc": "2026-08-24T00:00:00+00:00",
              "gate": {"identity_verified": True}, "disqualifiers": [],
              "case_facts": {}, "gate_cleared": False}
    status, body = _post(base_url, "/api/triage", record)
    assert status == 200
    assert str(body.get("status", "")).startswith("BLOCKED")


def test_triage_class_b_end_to_end_through_real_modules(base_url):
    record = {"case_id": "CASE-WEB-B", "created_utc": "2026-08-24T00:00:00+00:00",
              "gate": CLEARED_GATE, "disqualifiers": [],
              "case_facts": {"seed_words_remembered": "3", "words_total": "12"},
              "gate_cleared": True}
    status, body = _post(base_url, "/api/triage", record)
    assert status == 200
    assert body["class"] == CLASS_B                      # partial-seed
    assert len(body["slots_placeholder"]) == 12
    assert body["estimate"]["n_words"] == 12
    assert body["verdict"] == verdict(body["estimate"])  # real estimate chain


# ─── protocol edges ──────────────────────────────────────────────────────────

def test_unknown_routes_return_404(base_url):
    try:
        _get(base_url + "/nope")
        raise AssertionError("expected HTTPError")
    except urllib.error.HTTPError as exc:
        assert exc.code == 404
    req = urllib.request.Request(base_url + "/api/nope", data=b"{}", method="POST")
    try:
        urllib.request.urlopen(req, timeout=10)
        raise AssertionError("expected HTTPError")
    except urllib.error.HTTPError as exc:
        assert exc.code == 404


def test_malformed_json_body_returns_400(base_url):
    req = urllib.request.Request(base_url + "/api/estimate-space",
                                 data=b"{not json",
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        urllib.request.urlopen(req, timeout=10)
        raise AssertionError("expected HTTPError")
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        assert "invalid JSON" in exc.read().decode("utf-8")
