# Breaking the live loop — curiosity's missing vector (A/B, rejected)

## The loop, root-caused

The live dashboard appeared to loop: the same right→up path to `(4,3)`, step to
`(4,4)`, reset, repeat — DI 1.0, zero governance blocks. The cause is **not** a
deadlock:

- `runtime.py` injects `curiosity_explore` with **no `action_vector`** (params
  carry only curiosity metadata).
- `GridAdpt.intent_to_action` → `legal_cardinal_action`: with no `preferred`
  vector it falls back to `legal_goal_step` (A* toward GOAL) over a **static**
  blocked set.
- So *every* selected intent — including curiosity — marches the same
  goal-routing step. The trajectory is identical each episode: a deterministic
  repeated *solve*, not a stuck state.

## Method (instrument-first)

Instrument: `telos/tools/exploration_audit.py` measures trajectory variety
(distinct positions, action transitions, distinct actions), mission (episodes,
progress/cycle), and safety/evidence (DI, blocks). Knob:
`PipelineConfig.curiosity_explore_probability` (default `0.0` = control); at
probability `p` each injected curiosity intent carries a seeded random unit
vector (`pipeline._rng`, deterministic under a fixed seed).

## A/B result (200 cycles)

| arm | positions | transitions | episodes | noop | prog/cyc | DI | blocks |
|---|---:|---:|---:|---:|---:|---:|---:|
| p=0.00 (control) | 8 | 73 | 21 | 11.5% | +0.0041 | 1.000 | 23 |
| p=0.15 | 9 | 77 | 21 | 11.5% | +0.0006 | 1.000 | 23 |
| p=0.30 | 13 | 97 | 17 | 14.5% | +0.0006 | 1.000 | 29 |
| p=0.50 | 19 | 96 | 18 | 17.5% | +0.0023 | 1.000 | 35 |
| p=1.00 (pure walk) | 21 | 125 | 13 | 16.5% | +0.0006 | 1.000 | 33 |

**Verdict: REJECT.** Every arm adds variety, but none adds it for free:
- `p=1.0` (a true random walk) collapses mission progress (episodes 21→13).
- `p≥0.30` loses episodes and increases blocks (safety).
- `p=0.15` is neutral on episodes/safety/DI and slightly more varied (8→9
  positions), but **doubles the steps per episode** (+0.0041 → +0.0006
  progress/cycle).

## Conclusion (decision)

**The loop is mission-efficient repetition, not a defect.** Determinism here is
the adapter routing every intent to the shortest legal goal path; making
trajectories *varied* necessarily trades mission efficiency. Per the acceptance
rule (variety up **without** degrading mission/safety), **no arm passes**, so
`curiosity_explore_probability` stays **default 0.0 (control)**.

The knob is retained and tested for operators who explicitly prefer variety over
efficiency (e.g., a demo/exploration mode): set
`config.curiosity_explore_probability = 0.15–0.2` for modest variety at equal
episode completion.

## Novelty-seeking (domain-side) — implemented

The random walk above lives in the **core** and ignores the domain. The
mission-aware alternative is **domain-side**: `GridAdpt(novelty_weight=w)` picks
the legal cardinal whose neighbor is **least visited**, tie-broken toward the
goal. `w=0` is control (goal A*); `w>0` explores coverage while still drifting
to the goal. Applies only to exploratory intents (`curiosity_explore` /
`novelty_seeking` metadata) with no preferred vector.

A/B (200 cycles, `telos/tools/exploration_audit.py --novelty 0,4,8,16`):

| arm | positions | transitions | episodes | prog/cyc | DI | blocks |
|---|---:|---:|---:|---:|---:|---:|
| nov=0 (control) | 8 | 73 | 21 | +0.0041 | 1.000 | 23 |
| nov=4/8/16 | **21** | **125** | 14 | +0.0030 | 1.000 | 25 |

Weight saturates at 4. Novelty covers the **whole grid** (8→21 cells) with
progress still positive (+0.0030, vs the random walk's +0.0006) — far better
than a core random walk — but ~30% fewer episodes in the window.

**Decision:** keep `novelty_weight=0.0` as the benchmark/gate default (mission
efficiency), and **enable `8.0` for the live dashboard demo** (where coverage,
not throughput, is the objective) via `TELOS_GRID_NOVELTY` (default 8.0 in the
producer; `0.0` restores goal-only routing). This directly fixes the reported
live loop: the agent now explores instead of repeating one path.

## LEFT

- `novelty_weight` stays 0.0 for benchmarks/gates (mission efficiency) and 8.0
  for the live producer (coverage). Tune with `TELOS_GRID_NOVELTY`.
- The deterministic loop remains the benchmark default by decision.
