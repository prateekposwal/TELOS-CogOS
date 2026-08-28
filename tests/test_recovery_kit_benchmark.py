"""benchmark.py tests — fast, synthetic, no key material."""
import json
import os

from recovery_kit.benchmark import (ENTROPY_BYTES, _candidate_from_entropy,
                                    _checksum_ok, benchmark,
                                    compare_to_presets)
from recovery_kit.space import load_wordlist


def test_checksum_validator_roundtrip():
    wl = load_wordlist()
    wl_index = {w: i for i, w in enumerate(wl)}
    for n in (12, 24):
        words = _candidate_from_entropy(os.urandom(ENTROPY_BYTES[n]), n, wl)
        assert _checksum_ok(words, wl_index, n) is True
        bad = list(words)
        j = 1 if words[0] != "abandon" else 0
        bad[j] = "zoo" if bad[j] != "zoo" else "zone"
        assert not _checksum_ok(bad, wl_index, n)


def test_benchmark_report_shape_and_sanity():
    rep = benchmark(n_words=12, gen_samples=300, pbkdf2_samples=4)
    assert rep["n_words"] == 12
    assert rep["pbkdf2_rounds"] == 2048
    for key in ("gen_phrases_per_sec", "pbkdf2_per_sec", "effective_seeds_per_sec"):
        assert rep[key] > 0
    assert rep["effective_seeds_per_sec"] <= min(rep["gen_phrases_per_sec"],
                                                 rep["pbkdf2_per_sec"])
    assert rep["bottleneck"] in ("generation+checksum", "pbkdf2-2048")
    json.dumps(rep)  # serializable for --json-out


def test_compare_to_presets_mentions_all_presets():
    rep = {"effective_seeds_per_sec": 100.0}
    lines = "\n".join(compare_to_presets(rep))
    for preset_name in ("cpu-8core", "gpu-budget", "gpu-flagship"):
        assert preset_name in lines
