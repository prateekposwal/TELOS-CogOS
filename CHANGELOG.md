# Changelog

All notable changes to TELOS are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
semantic versioning.

## [Unreleased]

### Fixed
- **Floating-point noise passed the significance gate.** With uncertainty-aware
  discrimination, a spread of ~1e-16 and an estimated SE of ~1e-17 produced a
  z-score ~8 → a false `STRUCTURAL_DISCRIMINATION`. Numerical noise is now
  floored (`spread <= 1e-9 → 0.0`) before the significance test. Found by the
  Identifiability Challenge (`experiments/identifiability_challenge/`), which
  compares TELOS's RESOLVED/ABSTAIN boundary against the Eberhardt/Hoyer/Scheines
  model-identifiability oracle (B identified by the interventional pair
  condition; Σe by a both-observed experiment). After the fix, agreement is 5/5.

### Added
- **Uncertainty-aware structural discrimination (Σe resolution).**
  `Hypothesis` gains an optional `predictor_se` (standard error of the
  prediction) and `CanonicalExperimentSelector` gains `z_threshold` (default 3):
  when every live hypothesis provides an SE, structural discrimination becomes a
  **significance test** (`spread / pooled_SE > z_threshold`); a non-significant
  difference returns `0.0` so the selector abstains (`NO_VALUE`) instead of
  choosing on noise. Without SEs the legacy raw-spread behavior is unchanged
  (fully backward compatible). This implements the RESOLVED finding that
  `feedback_shared` vs `persistence_feedback` are identifiable from the
  **continuous observational Σe statistic** (lag-8 autocorrelation averaged over
  episodes) — the prior `NO_VALUE` was a `{0,1}`-threshold artifact. Verified:
  continuous discrimination 0.132, z=4.3, selector picks the observational
  experiment and resolves; thresholded control 0.0.

### Added
- **Temporal/state experiment primitive support (V14b).**
  `CanonicalExperimentSelector.structural_discrimination` now accepts
  **trajectory** predictions (a temporal/multi-step probe) as well as scalars,
  applying the SAME max-min spread per time-step — the selection policy and
  decision VoI are unchanged. This lets a domain-neutral temporal probe be
  expressed as an experiment via a hypothesis predictor. Blind campaign: with
  intervention/noise sampling **aligned** (the pulse harness had drawn noise only
  on the non-intervened branch, desynchronizing the A/B RNG streams and
  contaminating trajectories), the temporal probe **resolves** `feedback` (1.0)
  and `feedback_delay` (→ `RESOLVED`); raw pulse separation 0.30, normalized-mean
  0.49. `feedback_shared` vs `persistence_feedback` remain `NO_VALUE` (genuine
  confounding). No oracle: delay≠feedback, shared-state≠feedback, and
  identical-hypothesis negatives all hold.

### Added
- **Structural discrimination in experiment selection (V14)**
  (`telos/core/discovery/experiment_selection.py`, extension — no new engine):
  `Hypothesis` gains an independent `structure` + `predictor` (its own predictive
  model, never the discovered structure); `CanonicalExperimentSelector` gains
  `structural_discrimination()`, `evaluate_structural()`, and `select_experiment()`
  with an explicit policy (reject unsupported/already-attempted → prefer canonical
  decision VoI when decision-relevant → else prefer the experiment that best
  distinguishes the live hypotheses by predicted outcomes → else `NO_VALUE`).
  `StructuralExperimentOption` reports `structural_discrimination_value` separately
  from decision VoI — no weighted coefficients. No repeated experiment; searches
  terminate (`RESOLVED`/`UNRESOLVED`/`NO_VALUE`/`EXHAUSTED`). Decisive falsifier
  passes (E1 indistinguishable → discrimination 0; E2 discriminating → selector
  chooses E2). Benchmark: `experiments/v14_structural_discrimination/`.

### Added
- **Compositional causal representation (V13)**
  (`telos/core/discovery/model_class.py`): bounded `CausalStructure` /
  `CausalRelation` / `discover_structure` — a *representation*, not an engine.
  Recurrence is a **directed cycle** (so a 3-cycle is depth-3, not "feedback"),
  components are connected subgraphs, and delay is a `temporal` relation (lag
  profile) preserved **alongside** recurrence. Bounded: `nodes ≤ 5`, `edges ≤ 8`,
  `depth ≤ 3`. `AcyclicModel`/`StatefulModel` operate over the same evidence.
  Falsifiers (3-cycle, two loops, feedback+delay), held-out compositional
  transfer, `delay ≠ feedback`, and observational-only `UNRESOLVED` all pass;
  V10/V11/V12 regressions clean. Benchmark:
  `experiments/assumption_discovery_v13_compositional/`.

### Fixed
- **Cycle membership conflated with downstream branches (R2).** `CausalStructure`
  now exposes `cycles` (directed cycles = SCCs of size≥2), `cycle_members`, and
  `downstream` (reachable from a cycle but not a member); `components` retains its
  explicit meaning (undirected connectedness). A node reachable from a recurrent
  cycle is no longer counted as a member unless it participates in a directed
  cycle. Required a separate *directed* adjacency (connectivity is undirected).
  3-cycle → `{v0,v1,v2}`; 3-cycle+branch → `v3` downstream only; two loops → two
  cycles; pure chain → no cycles. Bounds unchanged; no new engine/planner/model
  class; `BOUND_EXCEEDED ≠ UNRESOLVED` and `representable ≠ identified` preserved.

### Fixed
- **Silent bound truncation in bounded causal representation (R1).** The bounded
  representation (`nodes ≤ 5`) silently truncated structures above the bound,
  reporting `representable=true` despite discarding information. Exceeding the
  node bound now returns an explicit `BOUND_EXCEEDED` status with an empty
  (non-misleading) graph and `representable=false`, while `UNRESOLVED` is kept
  strictly for epistemic uncertainty (representable but not identifiable).
  New `CausalStructure.bound_exceeded` / `.status` / `.representable` /
  `.n_observed`; `reported_nodes == represented_nodes` always. R2 (cycle vs
  acyclic branch) deliberately left as a known limitation.

### Fixed
- **Observational-only structure fabrication (V12).** `StatefulModel` could emit a
  `shared_state` CANDIDATE from association + autocorrelation without any
  intervention. It now requires an observed intervention before asserting ANY
  structure; observational ambiguity remains `UNRESOLVED`. Found by the V12
  compositional/adversarial transfer campaign (Outcome C: fix discrimination
  semantics, not add a model class).

### Added
- **Compositional + adversarial transfer campaign (V12)**
  (`experiments/assumption_discovery_v12_transfer/`): unseen composed structures,
  adversarial near-neighbors, intervention-sufficiency, 10 seeds × 3 noise.
  Held: `delay ≠ feedback`, genuine feedback, state persistence, adversarial
  distinction. Failure surface: **pairwise representation collapses composed /
  N-ary / deep recurrence** (feedback+delay and feedback+shared-state → `feedback`;
  3-node loop read as 2-node; `multiple_loops` misclassified). No new architecture.

### Added
- **Stateful / feedback model-class extension (V11)**
  (`telos/core/discovery/model_class.py`): one `ModelClass` contract
  (`represent/predict/intervene/explain/falsify/admissible_structure`) with
  `AcyclicModel` (V10 behavior preserved) and `StatefulModel` — an extension, not
  a new engine. `StatefulModel` represents genuine `feedback` (both interventions
  move) and `shared_state` (association + persistence but null interventions),
  keeping `MODEL_CLASS_INSUFFICIENT` first-class for the acyclic class. Critical
  falsifier: **`delay ≠ feedback`** (delayed-direct stays SUFFICIENT). The exact
  V10 transfer suite is unchanged (no false feedback). Generated structures stay
  `UNVALIDATED`. Benchmark `experiments/assumption_discovery_v11/`.

### Added
- **Blind cross-domain transfer (V10)** (`telos/core/discovery/model_class.py`):
  a README-level question — does the V3–V9 stack transfer to unseen domains with
  **no domain-specific hypothesis vocabulary**? `assess` uses only generic
  primitives (correlation, lag, intervention effects, autocorrelation) and emits
  SUFFICIENT / ADDITIONAL_STRUCTURE_REQUIRED / UNRESOLVED / **MODEL_CLASS_INSUFFICIENT**.
  Across 8 synthetic hidden domains (dev/holdout split) × 5 seeds → verdict
  accuracy **1.0**; feedback (`X↔Y`) is correctly flagged MODEL_CLASS_INSUFFICIENT
  (distinct from UNRESOLVED on noise); delayed-direct/nonlinear/noise invent
  nothing. The acyclic model class is the demonstrated boundary.

### Added
- **Hypothesis-space expansion under bounded search (V9)**
  (`telos/core/discovery/structure_invention.py`): `StructureInventor` invents
  previously-absent structural candidates (including an *unnamed* intermediate)
  from a bounded vocabulary {direct, direct_delay, mediated, common_cause},
  distinguishing three hidden worlds (direct-delay / mediation / common-cause).
  An invented entity enters as **HYPOTHESIZED** (never OBSERVED; `VariableStatus`);
  a **complexity cost** gives Occam preference so a latent is added only when the
  evidence requires it; equal-complexity ambiguity stays **UNRESOLVED** (no
  promotion); noise/direct/delayed-direct invent nothing; the hidden variable name
  is never emitted. Links to V6 (the invented structure creates a future
  experiment the planner then values). Benchmark
  `experiments/assumption_discovery_v9/`.

### Added
- **Hypothesis generation from unexplained evidence (V8)**
  (`telos/core/discovery/hypothesis_generation.py`): `HypothesisGenerator` turns
  an unexplained residual (a significant, repeatable lag) into CANDIDATE
  explanations (delayed-direct vs mediated) that enter as **UNVALIDATED** — never
  believed. It refuses to generate on noise or lagless correlation, discriminates
  the two candidates with an experiment (one eliminated), and never emits a hidden
  variable name. Benchmark `experiments/assumption_discovery_v8/`: hidden `X→M→Y`
  (M hidden) with a 2-step lag is detected from a 0.05 contemporaneous
  correlation; the mechanism is recovered; the hidden mediator is never named.
  Hypothesis-space EXPANSION (inventing the latent variable) remains open.

### Added
- **Causal planner integration (V7)** (`telos/core/discovery/causal_planner.py`):
  `CausalPlanner` builds the planner model from the REAL stack — immediate values
  from `CanonicalExperimentSelector` → `CounterfactualEngine`, successors from the
  hypotheses' own predicted outcomes, evidence-gated candidate generation — with
  no second valuation mechanism (`PlannerAwareSelector` supplies lookahead only).
  Honest result: the real integration does **not** reproduce V6's synthetic
  divergence, because the "unlocking" experiment has **zero** canonical decision
  sensitivity; planner-aware selection collapses to greedy. Planning is provably
  **pure** (never mutates RealityGapTracker/Evidence/TheoryBuilder/KnowledgeGraph).
  Adds the **safe-write guard** (`telos/tools/safe_write.py`: `safe_create` refuses
  to clobber, `safe_modify` requires existing) against accidental file overwrites.

### Added
- **Planner-aware Value of Information (V6)** (`telos/core/discovery/planner.py`):
  `PlannerAwareSelector` EXTENDS the canonical immediate VoI (V3) with expectimax
  lookahead, exposing two modes `GREEDY` and `PLANNER_AWARE`. At horizon 1 the
  planner is identical to greedy; at H>1 it diverges where an experiment's value
  lies in the future experiments it unlocks. Adversarial benchmark
  (`experiments/assumption_discovery_v6/`): unlocking (greedy A=4.0 vs planner
  B=9.0), bottleneck (Z=2.0 vs X=5.0), budget trap (A=5.0 vs B=7.0); the
  decisive falsifier — same initial state, different observation ⇒ different next
  plan; an unaffordable decisive experiment yields UNRESOLVED (never forced
  confidence); the planning model carries no ground truth. 7 falsifier tests.

### Added
- **Scaled causal-discovery failure surface (V5)**
  (`experiments/assumption_discovery_v5/`): hidden SCMs with opaque variable names
  across 5/7/10 variables, 9 families (chain/fork/collider/confounders/latent/
  nonlinear/stochastic/mixed/decoy), noise tiers, and 10 seeds. Reuses
  `CausalProbe` (no second engine). Result: as variables grow, **graph-frame
  precision degrades** (0.735 → 0.645) and the **false-causal rate rises**
  (0.265 → 0.355) — the intervention probe measures *total* (mediated) effects —
  while **decision-frame recovery stays ≈1.0**. A **false-certainty test** shows a
  latent-induced association stays `OBSERVED_CORRELATION` (UNRESOLVED) until one
  discriminating intervention moves it to `SUPPORTED`. A **decoy** with higher
  correlation than the true cause is correctly avoided by the canonical
  (effect-based) selection. Leakage audit passes (opaque names, sample-only
  surface, truth/latent hidden). Adds a false-certainty transition test.

### Added
- **Adaptive experiment sequences (V4)** (`telos/core/discovery/adaptive.py`):
  `AdaptiveExperimentPlanner` wraps the canonical selector in an adaptive loop —
  each next experiment is chosen from the UPDATED state (never precomputed), with
  an explicit stopping policy (resolution / confidence / no-value / contradictory
  / experiment-budget / cost-budget) and hard budget bounds. New evidence changes
  the next experiment (same initial state, observation 0 → `[H1,H2]`; observation
  1 → `[H1]`); a previously-valuable experiment is not run once falsified; a large
  Reality Gap re-routes selection. Reuses CanonicalExperimentSelector,
  RealityGapTracker, TheoryBuilder, KnowledgeGraph. Benchmark
  `experiments/assumption_discovery_v4/` (multi-seed).

### Changed
- **Canonical counterfactual value (V3)**: experiment selection now flows through
  ONE authoritative mechanism — `CanonicalExperimentSelector`
  (`telos/core/discovery/experiment_selection.py`) →
  `CounterfactualEngine.compute_value_of_information()`. The duplicated
  `CausalProbe.decision_sensitivity` was removed; `CausalProbe` is now purely
  discovery/classification. Unvaluable hypotheses are reported as UNKNOWN (never
  zero-value), and if every candidate is unvaluable the selector returns None.
  Ablation (`experiments/assumption_discovery_v3/`) shows the canonical engine
  changes the selected experiment (decisive arm B vs uncertainty-only arm A), and
  an unvaluable candidate is never selected.

### Added
- **Adversarial Causal Discovery (V2)** (`telos/core/discovery/causal_probe.py`):
  a `CausalProbe` that EXTENDS the assumption-discovery architecture with an
  epistemic ladder (`OBSERVED_CORRELATION` / `CAUSAL_HYPOTHESIS` /
  `SUPPORTED_CAUSAL_RELATION` / `FALSIFIED_RELATION` / `UNRESOLVED_RELATION`),
  intervention-based (do-calculus) direction resolution with a significance test,
  and decision-relevant information value (sensitivity × uncertainty ÷ cost).
  A 9-world hidden difficulty ladder (`experiments/assumption_discovery_v2/`)
  yields causal precision/recall/direction/unresolved = 1.0 across direct,
  reverse, confounding, multi-hop, latent, nonlinear, conditional, and stochastic
  worlds; the correlation-only baseline acts on causally-inert decoys 2/8 vs the
  engine 0/8. TheoryBuilder promotion reached legitimately (thresholds unchanged);
  the changing world re-learns via RealityGapTracker with no manual reset.

### Added
- **Assumption Discovery (research prototype)** (`telos/core/discovery/`): given
  only (state, action, next_state, reward, done), `AssumptionDiscoverer` proposes
  candidate variables → relationships → assumptions, each with a **falsifiable
  test**, an information value (relevance × uncertainty × falsifiability ÷ cost),
  and evidence-gated promotion. Reuses `EvidenceInfo`, `RealityGapTracker`,
  `KnowledgeGraph`, `TheoryBuilder`; declared vs discovered assumptions are kept
  structurally distinct (no silent promotion). Benchmark
  (`experiments/assumption_discovery/`) recovers a hidden 2×2 control map
  (recall/precision/sign-accuracy 1.00), falsifies stale assumptions after a
  domain flip, transfers to an unseen domain, and beats random/identity baselines
  on decision quality.

### Added
- **Executable decision graph** (`telos/core/handoff/graph.py`): `DecisionRecord`
  gains typed `assumption_refs` / `depends_on` / `guarded_deps`, plus
  `AssumptionRegistry` (stable IDs → text) and `DecisionGraph` with
  `affected_decisions(G)` — the exact set to revisit when an assumption changes,
  by graph traversal (guarded, non-propagating edges excluded). Wired into
  `DecisionStore` (`write_registry`/`load_registry`/`graph`) and the CLI
  (`decision_records.py affected <G>`). Turns the scale-experiment result into a
  native TELOS capability.
  - **Live feed:** `AssumptionRegistry` carries *bindings* (intent type / domain
    → assumption IDs); `DecisionRecorder` resolves them so live cycles populate
    `assumption_refs` automatically, and persists the registry beside the store.
    Opt-in via `TELOS_DECISION_STORE` + `TELOS_DECISION_ASSUMPTIONS` (default
    off → no refs, byte-identical).
- **Jev habits wired** (`telos/core/handoff/schema.py` + record):
  **calibrated confidence** (`DecisionRecord.calibrated_confidence` — the honest
  empirical number, attached by the recorder from the `CalibrationTracker`);
  **typed/closed outputs** (`validate_record` / `is_valid` / `assert_valid` /
  `schema_dict`, with closed enums for status/evidence source/validation);
  **no malformed results** (`DecisionStore.write` refuses to persist a record
  that fails the schema, unless `validate=False`).
- **Context Handoff (experiment)**: `DecisionRecord` (`telos/core/handoff/`) —
  a portable, agent-agnostic decision artifact that preserves the *reasoning*
  (objective, evidence with provenance, assumptions, constraints, alternatives
  + rejection reasons, expected consequences, and executable revalidation
  conditions), not just the answer. Composes existing types (`EvidenceInfo`,
  `IntentIR`, `DecisionTrace`/`PhaseContext`, `ProjectNode`,
  `ModelRealityGap`); serializes deterministically to JSON and markdown;
  `apply_reality_gap()` drives revalidation from the pipeline's own
  falsification state.
- **`DecisionRecorder`** emits a record for **meaningful decisions only**
  (a new committed intent type, or a new governance signature) from the REFLECT
  phase — observational, runs alongside `AGENTS.md`, never replaces it. Exposed
  via `pipeline.decision_records()` / `pipeline.decision_recorder`.
- **`DecisionStore` + `telos/tools/decision_records.py`** — the minimal
  file-backed exchange: records persist as `decision_records/<id>.json`, any
  context can list/search/read them, and `revalidate()` flips contradicted
  decisions to `FALSIFIED` on disk. Opt-in via `TELOS_DECISION_STORE=<dir>`
  (unset = in-memory only). Proves the exchange loop end-to-end without a
  server.
- **Decision Calibration (System One borrow)**: `CalibrationTracker`
  (`telos/core/calibration/`) records `(claimed confidence, realized outcome)`
  per cycle and reports Brier score, Expected Calibration Error, a reliability
  curve, and a recalibration map. The snapshot is attached to every
  `DecisionTrace` via `reflection.calibration`; `pipeline.calibration_report()`
  exposes it.
- **`CalibrationValidator`** (`telos/core/council/validators/calibration.py`):
  blocks an overconfident + miscalibrated claim. **Advisory by default**
  (zero-weight abstention — DI/voting/escalation unchanged); `enforce=True`
  is the opt-in governance intervention. Wired into the canonical GridWorld
  builder in advisory mode.
- **`telos/tools/calibration_pressure_test.py`** + `tests/core/test_calibration*.py`:
  a controlled scenario matrix (well-calibrated / overconfident /
  underconfident / ECE below-above threshold / insufficient data) proving
  `enforce=True` blocks **only** overconfidence and advisory blocks nothing,
  plus a pipeline A/B measuring action-emission, DI, and escalation.

## [0.2.0] — 2026-09-18

### Added (Phases 1–3 — capability uplift)
- **Phase 1 tool use (3.0 → 5.0)**: `NetworkSandbox` — the one governed egress
  channel (host/port/route allowlist, https-only except loopback, bounded
  payloads, no redirects); the `network_read` tool family (`http_get`/
  `http_post`) with capability profiles requiring `causal_confidence`; the
  producer enables `per_tool_capability_gate`.
- **Phase 2 memory (3.5 → 5.0)**: no — memory shipped in 0.1.0's Unreleased
  work; see below. (Kept accurate: tiered decision memory + controller +
  measured retrieval landed before this release.)
- **Phase 3 learning (3.0 → 4.5)**: `SkillAcquisition` (a skill enters the
  library only after a verification signal — the fix-loop rule generalised);
  `Curriculum` (deterministic novelty-ordered tasks, ZPD frontier);
  `learning_curve` measured against a frozen control (5 vs 2 successes, slope
  +0.021 vs −0.110, 3 transfers).
- **Phase 4 maturity (3.1 → 4.0)**: `examples/quickstart.py`, `RELEASE.md`
  (semver policy + release checklist), version lock (`tests/core/test_version.py`),
  capability gates wired into CI and `make check`.
- **Packaging**: installable as `telos-cogos`; `telos` console script and
  `python -m telos`; `telos run --cycles N`.

### Fixed
- **`TelemetryCollector.record_phase_failure` did not exist** — a phase crash
  raised `AttributeError` that masked the real error, turning a handled failure
  into a mystery. Added (records the failure as a tagged telemetry point).
- **`PatternLibrary.save` lost the checkpoint** on any set/numpy metadata
  ("Object of type set is not JSON serializable"), and `load` rebuilt the
  domain/type indices as `set`s while callers `.append()` to them
  (`AttributeError: 'set' object has no attribute 'append'` on reload).
  Both fixed at the one serialization site (`_json_safe` + list-contract load).
- **`recovery_kit` checksum-roundtrip flake**: the test's fixed word-substitute
  could coincidentally satisfy the BIP-39 checksum (~6.4% of trials for n=12),
  flaking ~1 in 3 full-suite runs. Now searches for a genuinely invalid
  substitution and asserts it found one (0/20000 false accepts).

## [0.1.0] — 2026-09-18

### Added (Phase 0 — Foundation)
- **Packaging**: `pyproject.toml` (PEP 621), a console entry point
  (`telos = telos.cli:main`), `LICENSE`, and `telos.__version__` — the project
  can now be installed with `pip install -e .` and run as `python -m telos`.
- **ToolRegistry** (`telos/core/actions/registry.py`): the executable tool set
  is now declared exactly once as `ToolSpec`s with a family taxonomy; the
  executor's `ACTION_ALLOWLIST` is a projection of it (one canonical source,
  no allowlist drift).
- **Tool-channel scanner** (`telos/tools/tool_channel_scan.py`): reports every
  production `subprocess`/`http.client` call site as governed, a documented
  known bypass, or unknown; `--ci` fails on any unknown (ungoverned) call.
- **Capability scorecard** (`telos/core/verifier/capability_scorecard.py` +
  `telos/tools/capability_scorecard.py`): computes the capability rubric from
  measured signals only, reports the four uplift baselines and their targets,
  and flags any score not backed by an external artifact.

### Fixed
- **CLI**: `telos status` no longer relies on a missing `telos.GENESIS` symbol;
  `telos run` no longer imports a nonexistent `telos.telos_task.run_pipeline`
  module — it now builds and runs a real GridWorld pipeline cycle. Added
  `python -m telos` support and a `--version` flag.
