# Changelog

All notable changes to TELOS are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
semantic versioning.

## [Unreleased]

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
