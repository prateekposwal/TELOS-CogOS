# TELOS v7 — Kernel + Stability Gate

> **Frozen 2026-08-29.** This document records the v7 architectural milestone:
> the Lightweight Kernel split, the two integrity classes, the performance
> contract, and the 10,000-cycle stability gate whose result table is the
> official baseline for the next generation.

---

## The single most important principle

> **"TELOS does not think deeply by default. TELOS earns the right to spend
> computation."**

The difference between a system that is merely *large* and one that is
actually *efficient*: ordinary work runs on the ~10ms fast path; hard problems
opt in to simulations, council, memory, KG traversal, and deeper reasoning —
proportionally to their difficulty.

## Two integrity classes (first-class TELOS principles)

Discovered over the v6→v7 cycle when two DIFFERENT bug classes were found and
fixed:

| Integrity | Question | Bug class it governs |
|---|---|---|
| **Epistemic integrity** | "Does TELOS believe the right thing for the right reason?" | The self-poisoning loop: governance blocks recorded as evidence → evidence reinforced the block → DI pinned at DissentFloor 0.3 for ~30k cycles. Fixed by the canonical rule *"governance suppression is not evidence; stale validation is not current falsification"* (`telos/core/governance/recovery_types.py`). |
| **Computational integrity** | "Does TELOS spend resources only when actually necessary?" | Structural perf bugs: full-trace serialization every cycle, global `np.random` leakage (12 sites), per-cycle 56K-edge KG serialization, quadratic theory rescans, unbounded retention. Fixed by the v7 kernel work below. |

The v7 stability gate protects BOTH: an optimization that weakens epistemic
integrity is not an optimization (proven by the SELF-POISON regression test).

## Architecture

```
                 ┌───────────────────┐
                 │    42 AXIOMS      │  compiled + hashed at startup;
                 │  immutable/hash   │  frozen; never re-parsed per cycle
                 └─────────┬─────────┘
                           │
                    ┌──────▼──────┐
                    │ TELOS KERNEL│  HOT PATH — only what the current
                    │             │  decision needs (mode gates + budgets)
                    │ Perceive    │
                    │ Reason      │
                    │ Evaluate    │
                    │ Select      │
                    │ Act         │
                    │ Reflect     │
                    └──────┬──────┘
                           │
                 ┌─────────▼─────────┐
                 │   DecisionTrace   │  immutable-ish, cheap, no hot-path copies
                 └─────────┬─────────┘
                           │
             ┌─────────────┼──────────────┐
             ↓             ↓              ↓
          Evidence      Governance       RNG       (structurally isolated)
             │             │              │
             └─────────────┼──────────────┘
                           ↓
                     EVENT BUFFER          → decision NEVER blocks on audit/dashboard
                           │
          ┌────────────────┼───────────────┐
          ↓                ↓               ↓
       Dashboard         Audit          Analytics
       async             async           async

  BEHIND THE KERNEL — OPTIONAL / LAZY SERVICES (cold path):
      Knowledge Graph (indexed, O(k) local ops, capped edges)
      Genealogy         Memory (HOT/WARM/COLD TTL + compaction)
      Counterfactual    Research / Debug instrumentation
```

### Hot path vs cold path (realized, measured)

The hot/cold split is realized through **mode gates** (`TELOS_MODE=fast|
standard|research|debug`) + **confidence/consequence budgets**, not a
standalone loader abstraction (profiling showed no need to build one — see
"deliberately not built").

Proven on the hot path per cycle (endurance-instrumented):
- traces serialized: **0.000/cycle** (contract ≤1) — was 1.003
- global RNG calls: **0** — was 12
- full KG/genealogy/evidence rebuilds: **0** (state-survives-identity tests:
  the same objects are reused across cycles)
- counterfactual work on confident cycles: **C_simulate ≈ 0**

## Performance contract (PASS — measured 2026-08-29)

Harness: `python3 telos/tools/perf_profiler.py --ci`

| Row | Target | Measured | Δ from baseline |
|---|---|---|---|
| Cold startup | <1.0s | **0.095s** | −61% |
| Health endpoint* | <50ms | **10.7ms** | — |
| Normal cycle mean | <100ms | **10.3ms** | −16% |
| Cycle p95 | <150ms | **12.1ms** | −35% |
| Memory idle | <150MB | **79.2MB** | −17% |
| Memory after 1000 cycles | ≈ idle ±10% | **bounded flat** | — |
| Checkpoint | <100ms | **79.1ms** | — |
| DecisionTrace serializations/cycle | ≤1 | **0.000** | fixed (was 1.003) |
| Global RNG | 0 | **0** | fixed (was 12) |
| Tests | ≥2590 | **2617** | +27 |
| Self-audit | 31/31 | **31/31** | — |
| Axioms | 42 | **42** | unchanged |
| DI / firewall | no regression | **1.0 sustained** | held |

\*Health row uses the producer's **cached scalar** (`/api/health` served from
the in-process snapshot), NOT a live-HTTP round-trip that can starve under
GIL load — the 0.002s direct value was the true endpoint; the earlier 168ms
"health probe" was a thrash artifact, not the endpoint.

## 10,000-cycle stability gate (PASS — the v7 barrier)

Harness: `python3 telos/tools/endurance.py --cycles 10000 --mode fast`
(result: `/tmp/telos_endurance_10k.json`)
Focused unit tests: `tests/core/test_endurance_invariants.py`

A REAL pipeline (fast mode: real runtime, streams, validators, governor,
firewall, evidence, KG, checkpointer — no stubs) held every invariant:

| Invariant | Measured | Expected | |
|---|---|---|---|
| DI stability (tail mean) | 0.594 | ≥0.5 | PASS |
| Memory stability (RSS drift) | 76.9MB, +3.8% | ≤+10% (leak) | PASS |
| RNG global hits | 0 | ==0 | PASS |
| Determinism (fixed seed, twice) | fingerprint identical | same | PASS |
| Trace/telemetry retention | 200 | ≤200 | PASS |
| KG node/edge caps | 1/229 | caps hold | PASS |
| KG adjacency symmetric | True | True | PASS |
| Checkpoint latency | 15.8ms | <100ms | PASS |
| Checkpoint retention | 10 files | ≤10 | PASS |
| Checkpoint chain (sparse) | True | True | PASS |
| Axioms | 42, 0 re-reads | 42, 0 | PASS |
| Firewall max trap streak | 2 | ≤50 (no infinite trap) | PASS |
| Designed escapes | 1386 | >0 when needed | PASS |

### What the gate caught and how it was fixed (v7.1)

The endurance gate was built to FIND degradation; it found three real patterns,
all fixed with pattern-first changes:

1. **TheoryBuilder quadratic rescan** (Λ4.7):
   `hypothesize()` ran an O(patterns × hypotheses) genexpr per cycle; with
   patterns growing ~1/cycle it hit **1.85M generator evaluations in one
   cycle** (309ms cycle at 3k cycles, unbounded growth). Fix: `_covered_patterns`
   + `_promoted_hypothesis_ids` indexes (O(1) checks), falsification releases
   coverage. **279.7ms → 8.2ms per cycle at the same point** (+34x).
2. **Theory retention caps**: patterns/hypotheses grew ~1/cycle forever.
   Bound each to `_max_history` with oldest-first eviction, index-synced.
3. **Unbounded retention leads (memory leak class)**: `DecisionMempool`
   `_confirmed`/`_rejected` grew 1/cycle each (2000→10000 MempoolEntry);
   SkillLibrary `_archived` only capped inside `prune()` (not the
   index_skill overflow path); resource-accounting `DictLedgerBackend`
   committed every cycle forever (20001 records); Assumption evidence lists
   grew per audit. All now bounded, oldest-first:
   - mempool `max_history=500`
   - skill `_archive()` helper caps `_archived`
   - `DictLedgerBackend(max_records=5000)` with per-cycle index pruned in lockstep
   - assumption evidence cap (50)
   - failure ledger default 10000→2000
   NET: 20k-cycle RSS **161MB → 101MB bounded**, no leak drift.
4. **Chain-check harness bug fixed, not the runtime**: sparse checkpoint
   chain was verified lexicographically (10000 sorted before 9820) → sorted by
   cycle. Runtime chain was always intact.

Memory stability is defined one-sided on purpose: **negative drift (GC /
compaction) passes**; only positive drift is a leak. The gate's RSS baseline is
the warm median, so process startup doesn't masquerade as a leak.

## Deliberately NOT built (documented decisions, not failures)

| Item | Decision | Why |
|---|---|---|
| Standalone lazy-loader abstraction | **Not built** | Mode gates + confidence budgets already realize the hot/cold split; profiling showed no need. Revisit only if profiling shows it. |
| Audit writer thread | **Not built** | The throttled atomic flush (5–25ms every 20 cycles, off the per-cycle path) is a measured non-issue. Decision log: bounded (500 cap / 250 keep), atomic tmp+rename. |
| `server_bridge.py` in runtime | **Not wired — on purpose** | MD-App bridge is a SIBLING service. The kernel must not import the app front-end. The gap scanner lists it in `INTENTIONAL_EXEMPTIONS` — the check still fails any NEW unimported module. |
| Chasing machine-level swap | **Not chased** | TELOS RSS is flat ~104MB. The ~2GB swap on an 8GB machine is the editor + Apple services being resident. "Fixing" TELOS to make the OS page graph prettier would make TELOS worse. Re-verify git mmap after an idle hour. |

## Frozen kernel (v7 stability barrier)

**Frozen as the baseline for the next generation:**
- kernel cycle behavior (7-phase pipeline in fast/standard modes)
- 42 axioms (compiled, hashed, immutable)
- self-audit 31/31 (a check may be added, never weakened)
- DI/firewall/stagnation invariants
- the performance contract above
- the SELF-POISON + endurance regression suites

**Gate to the next generation:** before adding Bayesian learning, autonomous
curiosity, or more council intelligence, the kernel must first answer *"Can
TELOS stay this fast, this small, and this epistemically clean while operating
continuously?"* If yes — that is a bigger milestone than another feature.

## How to run

```bash
# Performance contract (asserts; exit 1 on miss)
PYTHONPATH=. python3 telos/tools/perf_profiler.py --ci

# 10,000-cycle stability gate
PYTHONPATH=. python3 telos/tools/endurance.py --cycles 10000 --mode fast --json /tmp/telos_endurance_10k.json

# Self-audit, tests
PYTHONPATH=. python3 telos/tools/self_audit.py
PYTHONPATH=. python3 -m pytest tests/ -q --tb=short
```