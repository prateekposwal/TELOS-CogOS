# Changelog

All notable changes to TELOS are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
semantic versioning.

## [Unreleased]

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
