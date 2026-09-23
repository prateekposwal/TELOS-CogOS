# Contributing to TELOS

Thank you for contributing to the TELOS project. TELOS is a mission-conditioned intelligence architecture; all contributions must adhere to our core axioms of **Constraint-First Intelligence** and **Health Conservation**.

## Core Principles
1. **Simulation-First**: All decision logic must be tested via counterfactual simulation.
2. **Stable Operating Region (SOR)**: No code may bypass the Safety Gate or push the system state outside the six-dimensional health bounds.
3. **Formal Invariants**: New components must not violate established formal invariants (Safety, Coherence, Liveness).

## Local Development Environment

Clone TELOS to a **local, non-iCloud-synced path** (e.g. `~/dev/telos`). On
macOS, "Optimize Mac Storage" evicts files under iCloud-synced
`Desktop`/`Documents`, which breaks git reads and the test suite — avoid those
locations.

Use a project-local interpreter rather than a bare `python3`, which may resolve
to one without the dependencies (numpy/pytest/flask/websockets):

```bash
/usr/bin/python3 -m venv --system-site-packages .venv
PYTHONPATH=. ./.venv/bin/python -m pytest tests/ -q
```

### Never commit personal or private-project docs

This repository is **public**. Do not commit personal documents (learning
plans, journals, poems), client/business names, or private project state.
Such files are gitignored on purpose (`REDACTED-LEARNING-PLAN.md`,
`*_PROJECT_STATE.md`, `telos/the_thread.md`, `learnings.json`, and similar) —
keep them local. The genesis creator recognition phrase is a secret; never
echo it into code, docs, or tests.

## Workflow
1. **Feature/Fix Branching**: Use descriptive branch names (e.g., `feature/manifold-clipping` or `fix/cfr-normalization`).
2. **Testing**: Before submitting, you must run the full test suite:
   ```bash
   PYTHONPATH=. ./.venv/bin/python -m pytest tests/ -q
   ```
3. **Benchmarks**: If you modify the simulation engine or performance-critical paths, you must run the TELOS Arena benchmarks and ensure no regression in Worlds/ms or Latency.

## Coding Standards
- **Typing**: All public methods must use strict type hints.
- **Documentation**: Complex logic must be documented in the corresponding architecture file (`TELOS_ARCHITECTURE_BENCHMARKS.md`).
- **Dependencies**: New dependencies must be approved and justified by the system's robustness requirements (prefer minimal/zero external dependencies).
