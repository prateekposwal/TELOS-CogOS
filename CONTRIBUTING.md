# Contributing to TELOS

Thank you for contributing to the TELOS project. TELOS is a mission-conditioned intelligence architecture; all contributions must adhere to our core axioms of **Constraint-First Intelligence** and **Health Conservation**.

## Core Principles
1. **Simulation-First**: All decision logic must be tested via counterfactual simulation.
2. **Stable Operating Region (SOR)**: No code may bypass the Safety Gate or push the system state outside the six-dimensional health bounds.
3. **Formal Invariants**: New components must not violate established formal invariants (Safety, Coherence, Liveness).

## Workflow
1. **Feature/Fix Branching**: Use descriptive branch names (e.g., `feature/manifold-clipping` or `fix/cfr-normalization`).
2. **Testing**: Before submitting, you must run the full test suite:
   ```bash
   python3 -m pytest
   ```
3. **Benchmarks**: If you modify the simulation engine or performance-critical paths, you must run the TELOS Arena benchmarks and ensure no regression in Worlds/ms or Latency.

## Coding Standards
- **Typing**: All public methods must use strict type hints.
- **Documentation**: Complex logic must be documented in the corresponding architecture file (`TELOS_ARCHITECTURE_BENCHMARKS.md`).
- **Dependencies**: New dependencies must be approved and justified by the system's robustness requirements (prefer minimal/zero external dependencies).
