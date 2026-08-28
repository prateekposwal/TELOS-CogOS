"""Throughput benchmark — quotes start from MEASURED numbers, not presets.

Lambda-2.3 (benchmark-before-quote): space.py THROUGHPUT_PRESETS are
conservative placeholders. This module measures what THIS machine can do
for the two stages that dominate a Class B (partial-seed) search:

  1. candidate generation + BIP-39 checksum validation (SHA-256 per phrase)
  2. mnemonic -> seed derivation (PBKDF2-HMAC-SHA512, 2048 rounds)

effective_seeds_per_sec ~= min(stage rates) — a targeted search only pays
PBKDF2 for checksum-passing candidates, so stage 2 is the usual ceiling on
CPU; GPU stacks shift the bottleneck but must be re-benchmarked ON THE RENTED
HOST before any client quote (TODO(verify) against btcrecover -m 9645 runs).

No key material ever passes through here: all targets are synthetic,
non-secret, and discarded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import time

PBKDF2_ROUNDS = 2048      # BIP-39 fixed
PBKDF2_DKLEN = 64         # BIP-39: 64-byte seed (512 bits)
ENTROPY_BYTES = {12: 16, 15: 20, 18: 24, 21: 28, 24: 32}


def _wordlist(path=None):
    from recovery_kit.space import load_wordlist, WORDLIST_PATH
    return load_wordlist(path or WORDLIST_PATH)


def _candidate_from_entropy(entropy: bytes, n: int, wl: list[str]) -> list[str]:
    """Forward BIP-39: entropy (+checksum bits) -> n words."""
    chk_bits = n // 3
    checksum = int.from_bytes(hashlib.sha256(entropy).digest(), "big") >> (256 - chk_bits)
    bits = (int.from_bytes(entropy, "big") << chk_bits) | checksum
    return [wl[(bits >> (n - 1 - i) * 11) & 0x7FF] for i in range(n)]


def _checksum_ok(words: list[str], wl_index: dict[str, int], n: int) -> bool:
    """Validation side of the same math an enumerator must run per candidate."""
    idxs = [wl_index[w] for w in words]
    bits = 0
    for i in idxs:
        bits = (bits << 11) | i
    chk_bits = n // 3
    ent_bits = n * 11 - chk_bits
    ent = (bits >> chk_bits).to_bytes(ent_bits // 8, "big")
    got = bits & ((1 << chk_bits) - 1)
    want = hashlib.sha256(ent).digest()[0] >> (8 - chk_bits)
    return got == want


def measure_generation_rate(n_words: int = 12, samples: int = 4000,
                            wl: list[str] | None = None) -> dict:
    """Phrases/sec for entropy->words->validate cycle (SHA-256 bound)."""
    wl = wl or _wordlist()
    wl_index = {w: i for i, w in enumerate(wl)}
    nbytes = ENTROPY_BYTES[n_words]
    urandom = os.urandom
    t0 = time.perf_counter()
    ok = 0
    for _ in range(samples):
        words = _candidate_from_entropy(urandom(nbytes), n_words, wl)
        if _checksum_ok(words, wl_index, n_words):   # always True by construction
            ok += 1
    dt = time.perf_counter() - t0
    if dt <= 0 or ok != samples:
        raise RuntimeError("generation benchmark failed sanity check")
    return {"samples": samples, "seconds": dt,
            "gen_phrases_per_sec": samples / dt}


def measure_pbkdf2_rate(samples: int = 24) -> dict:
    """Derivations/sec for the 2048-round PBKDF2-HMAC-SHA512 seed step."""
    pw = b"recovery_kit synthetic benchmark password (not a secret)"
    salt = b"mnemonicsynthetic-salt-for-benchmarking-only"
    pbkdf2 = hashlib.pbkdf2_hmac
    times = []
    for i in range(samples):
        s = salt + i.to_bytes(4, "big")
        t0 = time.perf_counter()
        pbkdf2("sha512", pw, s, PBKDF2_ROUNDS, dklen=PBKDF2_DKLEN)
        times.append(time.perf_counter() - t0)
    med = statistics.median(times)
    return {"samples": samples, "median_seconds": med,
            "pbkdf2_per_sec": 1.0 / med}


def benchmark(n_words: int = 12, gen_samples: int = 4000,
              pbkdf2_samples: int = 24) -> dict:
    gen = measure_generation_rate(n_words, gen_samples)
    kdf = measure_pbkdf2_rate(pbkdf2_samples)
    effective = min(gen["gen_phrases_per_sec"], kdf["pbkdf2_per_sec"])
    bottleneck = ("generation+checksum" if effective == gen["gen_phrases_per_sec"]
                  else "pbkdf2-2048")
    return {
        "n_words": n_words,
        "pbkdf2_rounds": PBKDF2_ROUNDS,
        "gen_phrases_per_sec": gen["gen_phrases_per_sec"],
        "pbkdf2_per_sec": kdf["pbkdf2_per_sec"],
        "effective_seeds_per_sec": effective,
        "bottleneck": bottleneck,
        "note": ("CPU measurement on this host; re-benchmark on the rented GPU "
                 "host before quoting (Lambda-2.3). TODO(verify) vs real "
                 "btcrecover/hashcat -m 9645 throughput."),
    }


def compare_to_presets(report: dict) -> list[str]:
    from recovery_kit.space import THROUGHPUT_PRESETS
    lines = []
    eff = report["effective_seeds_per_sec"]
    for name, preset in sorted(THROUGHPUT_PRESETS.items()):
        gap = preset / eff if eff else float("inf")
        lines.append(f"  {name:<12} preset {preset:>9,.0f}/s  "
                     f"= {gap:,.1f}x this machine's measured rate")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Measure local search throughput (quotes start measured)")
    ap.add_argument("--words", type=int, default=12, choices=sorted(ENTROPY_BYTES))
    ap.add_argument("--gen-samples", type=int, default=4000)
    ap.add_argument("--kdf-samples", type=int, default=24)
    ap.add_argument("--json-out", help="also write full report JSON to PATH")
    args = ap.parse_args(argv)

    report = benchmark(args.words, args.gen_samples, args.kdf_samples)
    print(f"measured on this host ({args.words}-word phrases):")
    print(f"  generation+checksum : {report['gen_phrases_per_sec']:>10,.0f} phrases/s")
    print(f"  pbkdf2-2048 derive  : {report['pbkdf2_per_sec']:>10,.0f} seeds/s")
    print(f"  EFFECTIVE rate      : {report['effective_seeds_per_sec']:>10,.0f} seeds/s "
          f"(bottleneck: {report['bottleneck']})")
    print("preset cross-check (space.py presets are placeholders until you run them"
          " on the actual attempt host):")
    for line in compare_to_presets(report):
        print(line)
    print(report["note"])
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(report, f, indent=2)
        print(f"report written: {args.json_out}")


if __name__ == "__main__":
    main()
