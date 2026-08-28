"""Search-space estimator — the feasibility engine that gates every case.

Pure math, no network, no key material ever touches this module.
Exact BIP-39 prefix counting via the bundled official wordlist
(data/bip39_english.txt, from bitcoin/bips).

HONESTY NOTES (Lambda-2.3):
  * The checksum divisor is the EXPECTED fraction of random mnemonics
    passing checksum (2^-n/3). With heavily constrained slots the true
    conditional rate differs; treat outputs as order-of-magnitude and
    re-benchmark throughput on your own hardware BEFORE quoting clients.
  * Throughput presets are deliberately CONSERVATIVE placeholders.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

WORDLIST_PATH = Path(__file__).parent / "data" / "bip39_english.txt"
CHECKSUM_BITS = {12: 4, 15: 5, 18: 6, 21: 7, 24: 8}  # n words -> checksum bits
# Conservative seeds/sec presets (VERIFY with hashcat -m 9645 / btcrecover first)
THROUGHPUT_PRESETS = {
    "cpu-8core": 20.0,
    "gpu-budget": 5_000.0,     # RTX 3060 / 2070 class, rented ~$0.15-0.30/hr
    "gpu-flagship": 50_000.0,  # RTX 4090 / A5000 class, rented ~$0.35-0.60/hr
}


def load_wordlist(path: Path = WORDLIST_PATH) -> list[str]:
    words = [ln.strip() for ln in Path(path).read_text().splitlines() if ln.strip()]
    if len(words) != 2048:
        raise ValueError(f"expected 2048-word list, got {len(words)} from {path}")
    return words


def slot_candidates(spec: str, wordlist: list[str]) -> int:
    """Slot DSL: 'word' literal | '?' any | 'prefix:xyz' | 'alt:a|b|c'."""
    if spec == "?":
        return len(wordlist)
    if spec.startswith("prefix:"):
        p = spec[len("prefix:"):].lower()
        return sum(1 for w in wordlist if w.startswith(p))
    if spec.startswith("alt:"):
        alts = [a for a in spec[4:].lower().split("|") if a]
        return max(1, len(set(alts)))
    w = spec.lower()
    if w not in wordlist:
        raise ValueError(f"slot '{spec}' is not a valid BIP-39 word (typo?)")
    return 1


def estimate(slots: list[str], unknown_order: int = 0,
             throughput: float = THROUGHPUT_PRESETS["gpu-flagship"],
             usd_per_gpuhr: float = 0.40):
    wl = load_wordlist()
    n = len(slots)
    if n not in CHECKSUM_BITS:
        raise ValueError("phrase must be 12/15/18/21/24 words")
    counts = [slot_candidates(s, wl) for s in slots]
    raw_combos = math.prod(counts)
    # Expected checksum filter (order-of-magnitude; see module notes)
    valid_est = max(1, round(raw_combos / (1 << CHECKSUM_BITS[n])))
    if unknown_order:
        valid_est *= math.factorial(min(unknown_order, 12))
    seconds_full = valid_est / throughput
    gpu_hours_full = seconds_full / 3600.0
    cost_usd = gpu_hours_full * usd_per_gpuhr
    return {
        "n_words": n, "slot_counts": counts,
        "raw_combinations": raw_combos, "valid_mnemonics_est": valid_est,
        "throughput_s": throughput, "usd_per_gpuhr": usd_per_gpuhr,
        "wallclock_days_full_space": seconds_full / 86400.0,
        "expected_days_half_space": seconds_full / 2.0 / 86400.0,
        "gpu_hours_full": gpu_hours_full, "compute_cost_usd_full": cost_usd,
    }


def verdict(res: dict) -> str:
    combos = res["valid_mnemonics_est"]
    if combos < 1e6:      return "VIABLE — hours or less; quote diagnostic immediately"
    if combos < 1e9:      return "VIABLE — days of GPU time; compute cost still trivial vs fee"
    if combos < 1e14:     return "LONG-SHOT — only accept with high wallet value + strong priors + deposit"
    return "REJECT — space too large absent extraordinary new information (Lambda-6.5 gate)"


def fee_viability(res: dict, value_usd: float, fee_rate: float,
                  assumed_success_prob: float) -> dict:
    """Break-even: accept iff P(success) x fee > compute cost (+ margin)."""
    expected_fee = value_usd * fee_rate
    cost = res["compute_cost_usd_full"]
    p_star = cost / expected_fee if expected_fee > 0 else float("inf")
    ev = assumed_success_prob * expected_fee - cost
    return {"expected_fee_usd": expected_fee, "p_star": p_star,
            "assumed_success_prob": assumed_success_prob, "ev_usd": ev,
            "accept_on_ev": ev > 0 and assumed_success_prob >= p_star}


def main(argv=None):
    ap = argparse.ArgumentParser(description="BIP-39 search-space estimator")
    ap.add_argument("--slot", action="append", required=True,
                    help="one per word: literal | ? | prefix:xyz | alt:a|b|c")
    ap.add_argument("--unknown-order", type=int, default=0,
                    help="k remembered-but-unordered words -> multiply by k!")
    ap.add_argument("--throughput-preset", default="gpu-flagship",
                    choices=sorted(THROUGHPUT_PRESETS))
    ap.add_argument("--throughput", type=float, help="override seeds/sec")
    ap.add_argument("--usd-per-gpuhr", type=float, default=0.40)
    ap.add_argument("--value-usd", type=float, help="client-stated wallet value")
    ap.add_argument("--fee-rate", type=float, default=0.10)
    ap.add_argument("--assumed-success-prob", type=float)
    args = ap.parse_args(argv)

    thr = args.throughput or THROUGHPUT_PRESETS[args.throughput_preset]
    res = estimate(args.slot, args.unknown_order, thr, args.usd_per_gpuhr)
    fmt = lambda x: (f"{x:.3g}" if isinstance(x, float) and abs(x) >= 1e12
                     else f"{x:,.4g}" if isinstance(x, float) else f"{x:,}")
    print(f"slots                : {res['slot_counts']}")
    print(f"raw combinations     : {fmt(res['raw_combinations'])}")
    print(f"valid mnemonics est  : {fmt(res['valid_mnemonics_est'])}")
    print(f"full-space wallclock : {res['wallclock_days_full_space']:,.2f} days @ {thr:,.0f} seeds/s")
    print(f"expected (half space): {res['expected_days_half_space']:,.2f} days")
    print(f"GPU-hours full       : {res['gpu_hours_full']:,.1f}  (~${res['compute_cost_usd_full']:,.2f})")
    print(f"VERDICT              : {verdict(res)}")
    if args.value_usd:
        p = args.assumed_success_prob if args.assumed_success_prob is not None else \
            (0.5 if res["valid_mnemonics_est"] < 1e9 else 0.15)
        fv = fee_viability(res, args.value_usd, args.fee_rate, p)
        print(f"fee viability        : exp.fee ${fv['expected_fee_usd']:,.0f}, "
              f"EV ${fv['ev_usd']:,.2f}, accept={fv['accept_on_ev']} "
              f"(P*={fv['p_star']:.4g})")


if __name__ == "__main__":
    main()
