# Falsifiable Theorems — TELOS claims restated as measured invariants

> **Why this document exists.** TELOS's original "theorems" were constructive
> existence proofs: *"a validator exists, therefore the axiom holds."* An
> existence proof of an implementation detail is not a prediction — it cannot
> be wrong, so it cannot be science. This document restates the load-bearing
> claims as **measurements with a declared null**: a metric, a threshold, and
> the behaviour that would falsify the claim. Every row is executed by
> `telos/tools/theorem_audit.py` on a real pipeline run, not asserted in prose.

Run it:

```bash
PYTHONPATH=. ./.venv/bin/python telos/tools/theorem_audit.py --cycles 40 --ci
```

Catalogued in code at `telos/core/verifier/theorem_audit.py::THEOREMS`.

---

## The audit table

| ID | Theorem | Measured metric | Passes when | Null (would falsify) |
|----|---------|-----------------|-------------|----------------------|
| **T1** | Determinism | sha256 fingerprint of two identically-seeded runs | fingerprints identical | fingerprints differ across identical seeds |
| **T2** | Process over Outcomes | `decision_integrity` per cycle | every DI ∈ [0, 1] | any cycle DI outside [0, 1] or missing |
| **T3** | Computational Conservation | `budget_consumed_ms / budget_total_ms` | max overrun ≤ 1.1× | any cycle consumes > 1.1× budget |
| **T4** | Possibility Preservation | `len(strategic_options)` per cycle | ≥ 1 alternative every cycle | a cycle stores zero alternatives |
| **T5** | Emergent Intelligence | activated streams per cycle | ≥ 2 streams every cycle | a cycle activates < 2 streams |
| **T6** | Kintsugi (System Memory) | matching vs unrelated intent after a recorded failure | matching blocked, unrelated passes, no-ledger passes | matching intent passes (failure logged, not integrated) |
| **T7** | Delayed Causality | `h_eff = max(h, τ+1)` | `h_eff > τ` | `h_eff ≤ τ` for some config |

### Measured baseline (2026-09-18, `--cycles 30`, standard mode)

```
T1-determinism          509eb8c632f1a2bb == 509eb8c632f1a2bb      PASS
T2-process              30/30 cycles in [0,1]                     PASS
T3-conservation         max overrun ratio=0.00 over 30 cycles      PASS
T4-possibility          min options=27                            PASS
T5-emergent             min activated streams/cycle=3             PASS
T6-kintsugi             matching blocked, unrelated passes        PASS
T7-delayed-causality    h_eff=5 > tau=0                           PASS
```

---

## What this fixes (and what it does not)

**Fixed:** the tautology. Each theorem now has a reachable null, exercised by
`tests/core/test_theorem_audit.py` (a sabotaged trace flips the row to FAIL).

**Honest limits:**
- T7's null is not reachable through configuration alone (the implementation
  computes `max(h, τ+1)` by construction); falsifying it requires mutating the
  implementation, which is covered by the *axiom* falsifier rather than here.
- T1–T5 measure the runtime's own traces. They detect regressions, not
  whether the metrics are the *right* metrics. That is the next layer of work
  (independent external reproduction — the D5 gate).

## Relationship to the axiom falsifier

- `telos/core/verifier/axiom_falsifier.py` attacks the **constitution**
  (42 axioms) by sabotaging each axiom's dependency — coverage 42/42.
- This document measures the **theorems** derived from the runtime — 7/7 hold.

Together they replace "green because nothing checked" with "green because an
adversary tried to make it red and failed."
