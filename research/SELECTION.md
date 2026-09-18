# The selection experiment — instrument, then let the data decide

Goal: understand why inquiry out-selects executable intents (~87%), and test
whether making **mission progress** an explicit selection signal increases
mission progress without degrading evidence or safety.

Method: instrument first (no behavior change), analyze, then a config-gated
A/B. Default stays `control` (byte-identical).

- Instrumentation: `telos/core/decision/selection_trace.py`
  (`SelectionDecision`, `IntentScoreBreakdown`, `mission_progress`), recorded
  on every `DecisionTrace`.
- A/B harness: `telos/tools/selection_audit.py --compare`.

---

## Phase 1 — Instrumentation (shipped, non-behavioral)

Per cycle the trace now carries: regime (`action`/`blended`/`inquiry`), raw and
effective Ω blend, Ω value + learned threshold, curiosity level, selected type,
and per-candidate `{select_score, mission_progress, is_inquiry, executable,
selected}`.

## Phase 2 — Analysis: the inversion is NOT in selection scoring

Real GridWorld workload, 150 cycles, control:

| Metric | Value |
|---|---|
| inquiry selected | **88.7%** |
| executable selected | 11.3% |
| no-op cycles | 70.0% |
| mission progress / cycle | +0.0351 |
| episodes completed | 5 |
| governance blocks | 42 |

The decisive measurement: **every candidate intent projects to the same legal
cardinal action**, so `mission_progress` is identical across candidates
(0.0218 for all — inquiry and executable alike). `mission_progress` therefore
carries **zero discriminative signal** here. The "inversion" is not
inquiry-vs-execution *score*; it is that inquiry intents are generated and
selected far more often.

Root cause of the no-op dwell (from `act.py`): `ctx.selected_action` is emitted
only when `firewall_passed AND council_ok AND not governance_blocked AND
governor_allows_act`. The 70% no-op is **ACT suppression** — governor
`DEFER` (`model_fidelity`) and `action_loop`/`low_integrity` governance blocks
— not a scoring preference for inquiry.

## Phase 3 — Minimal, bounded, gated change (shipped)

`PipelineConfig.selection_policy`, default `"control"` (no behavior change):
- `mission_progress` — damp the inquiry blend by the best executable
  candidate's progress (bounded to 0.6).
- `mission_progress_readiness` — damp only when a high-confidence executable
  candidate exists (enough information to act).

Tests: `tests/core/test_selection_policy.py` (control inert; damping bounded;
readiness gated; all-inquiry inert; zero-progress inert).

## Phase 4 — A/B pressure test: NULL RESULT (honest)

```
control                     exec=11.3% inquiry=88.7% noop=70.0% prog/cyc=+0.0351 episodes=5 DI=0.921 gov=42
mission_progress            exec=11.3% inquiry=88.7% noop=70.0% prog/cyc=+0.0351 episodes=5 DI=0.921 gov=42
mission_progress_readiness  exec=11.3% inquiry=88.7% noop=70.0% prog/cyc=+0.0351 episodes=5 DI=0.921 gov=42
=> NO EFFECT
```

The bounded damping (~1.3%, from a ~0.02 progress signal) is below the
workload's noise floor. **The mission-progress hypothesis is rejected by its
own instrument.** Evidence quality and safety are unchanged (no regression),
but neither is mission progress improved.

## What this tells us (the real lever)

```
   Intent Generation  ──►  SELECT/J  ──►  Execution (ACT)  ──►  Backstop
        (fine)            (not the       🔴 governor DEFER /     (guardrail)
                           bottleneck)     governance blocks
```

The next real throughput task is **ACT suppression**, not selection scoring:
- quantify why `model_fidelity` DEFERs so often (validated model fidelity <0.5,
  or untested-in-partial-observability);
- decide whether the act-then-learn window is too tight for a partial-obs world.

Only after ACT emits actions does selection priority become the binding
constraint.

## Phase 4b — corrected harness (the episode-reset artifact)

The ACT-gate instrument then revealed a **measurement bug in the benchmark
harness itself**: the drivers reset the GridWorld state to the origin on
terminal (`goal`) WITHOUT signalling the episode to the pipeline. The model had
predicted a landing near the goal; the next observation was the origin → a huge
spurious reality gap → `model_fidelity` collapsed → the ACT gate DEFERred.

The live producer does this correctly (`episode_reset=True` on the next
`execute`). The shared driver is now `telos/tools/bench_loop.py` (the one
correct loop).

| Metric | Flawed harness | Corrected (`episode_reset`) |
|---|---:|---:|
| action emitted | 30.0% | **55.3%** |
| `model_fidelity` DEFERs | 92/150 | **0/150** |
| model fidelity (mean) | 0.455 | **1.000** |
| no-op rate | 70.0% | **44.7%** |
| episodes completed | 5 | **10** |

So the "model_fidelity is the bottleneck" reading was **mostly a harness
artifact** — instrument-first caught it before any gate was changed. What
remains after correction:

- inquiry still out-selects executable intents (~89%) — real, but the A/B is
  still **null** (mission_progress non-discriminative);
- the remaining ~45% no-op is **firewall governance** (`low_integrity` ≈40,
  `action_loop` ≈27) + inquiry dwell — not capability DEFER.

## Honest status

- Phase 1–3: **shipped** (instrumentation + gated policy + tests).
- Phase 4: **null result, documented** (mission_progress non-discriminative;
  policy inert).
- Phase 5: coverage breakdown in `research/COVERAGE.md`.
