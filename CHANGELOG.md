# Changelog

All notable changes to TELOS are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
semantic versioning.

## [Unreleased]

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
