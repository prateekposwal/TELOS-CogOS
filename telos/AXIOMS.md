# TELOS — 20 Axioms of Systemic Intelligence

## Layer 1: Architectural Invariance
| # | Axiom | Meaning | Implementation |
|---|-------|---------|----------------|
| 1.1 | Architecture Produces Outcomes | The pipeline is a pure structural engine; outputs are determined by architecture, not heuristics | `runtime.py` — 7-phase pipeline |
| 1.2 | Process over Outcomes | DecisionTrace captures integrity, not just results | `DecisionTrace` — DI, MD, council signals |
| 1.3 | Multi-Level Governance | TrustManager authorizes streams at mission context level | `trust_manager.py` — `authorize_knowledge_release()` |

## Layer 2: Feedback & Memory
| # | Axiom | Meaning | Implementation |
|---|-------|---------|----------------|
| 2.1 | Governance First | ReadinessEngine and ConstraintValidator check before action | `timing.py`, `validators.py` — `InformationReadinessEngine` |
| 2.2 | Feedback Loops | InfraManager observes results and adjusts parameters | `infrastructure_manager.py` — `observe()` → calibration |
| 2.3 | Kintsugi | Failures are recorded as structural assets, not discarded | `failure_ledger.py` — `FailureRecord` + root-cause tracking |
| 2.4 | Path Dependency | All decision functions are history-aware | `world_ledger.py`, `planning_horizon.py` |
| 2.5 | Delayed Causality | Adaptive horizon adjusts simulation depth based on stability | `infrastructure_manager.py` — `adaptive_horizon` |

## Layer 3: Adaptive Capacity
| # | Axiom | Meaning | Implementation |
|---|-------|---------|----------------|
| 3.1 | Maintenance vs Recovery | Tighten policy on failure; restore on stability | `infrastructure_manager.py` — `enter_recovery()`/`exit_recovery()` |
| 3.2 | State Maintenance | BudgetManager reserves slices for lower-priority streams | `attention.py` — `reserve()`/`check_budget()` |
| 3.3 | Option Decay | Skills not matched within prune_age_cycles are archived | `skill_library.py` — `prune()` |
| 3.4 | Exploration vs Exploitation | UCB + Thompson sampling for domain exploration | `mission_policy.py` — `exploration_bonus()`, `thompson_sample()` |
| 3.5 | Structural Inertia | Non-selected streams get influence boost to compete | `stream_calibrator.py` — `influence_weight *= 1.08` on non-selection |

## Layer 4: Emergent Intelligence
| # | Axiom | Meaning | Implementation |
|---|-------|---------|----------------|
| 4.1 | Identity Shapes Decisions | SemanticDepth 4-layer ladder; SystemSelf mood affects risk | `system_self.py`, `world_ledger.py` |
| 4.2 | Exploration/Comfort Trade-off | System balances known-safe vs novel actions | `mission_policy.py` — risk/exploration params |
| 4.3 | Possibility Preservation | CounterfactualEngine always generates alternatives | `simulation.py` — `|F_t| >= 1` |
| 4.4 | Structural Resilience | DecisionFirewall provides pre-execution reality audit | `firewall.py` — `inspect()` |
| 4.5 | Local vs Global Optima | StreamCalibrator detects dominant-stream lock-in | `stream_calibrator.py` — `is_stuck()`, `forced_exploration_stream()` |
| 4.6 | Emergent Intelligence | No single stream is "I"; coordination = intelligence | `synthesize.py` — `SynthesisPhase` merges intents |
| 4.7 | Law of Attention and Trajectory | Attention allocation → counterfactual generation → trajectory shape | `core/attention/projection.py` — `AttentionProjectionEngine`, `allocate_attention_budget()` |

## Layer 5: Commitment Theory
| # | Axiom | Meaning | Implementation |
|---|-------|---------|----------------|
| 5.1 | TELOS Commitment | `C* = argmax[E(R) - M - Rec - I + F]` — commitment modulated by maintenance cost, recovery cost, identity cost, and future opportunity preservation | `SelectPhase` — `commitment_mod = identity_gate × cost_gate × diversity_bonus` |

---

## Index by Axiom Number

| # | Short Name | Layer |
|---|------------|-------|
| 1.1 | Architecture Produces Outcomes | 1 — Architectural Invariance |
| 1.2 | Process over Outcomes | 1 — Architectural Invariance |
| 1.3 | Multi-Level Governance | 1 — Architectural Invariance |
| 2.1 | Governance First | 2 — Feedback & Memory |
| 2.2 | Feedback Loops | 2 — Feedback & Memory |
| 2.3 | Kintsugi | 2 — Feedback & Memory |
| 2.4 | Path Dependency | 2 — Feedback & Memory |
| 2.5 | Delayed Causality | 2 — Feedback & Memory |
| 3.1 | Maintenance vs Recovery | 3 — Adaptive Capacity |
| 3.2 | State Maintenance | 3 — Adaptive Capacity |
| 3.3 | Option Decay | 3 — Adaptive Capacity |
| 3.4 | Exploration vs Exploitation | 3 — Adaptive Capacity |
| 3.5 | Structural Inertia | 3 — Adaptive Capacity |
| 4.1 | Identity Shapes Decisions | 4 — Emergent Intelligence |
| 4.2 | Exploration/Comfort Trade-off | 4 — Emergent Intelligence |
| 4.3 | Possibility Preservation | 4 — Emergent Intelligence |
| 4.4 | Structural Resilience | 4 — Emergent Intelligence |
| 4.5 | Local vs Global Optima | 4 — Emergent Intelligence |
| 4.6 | Emergent Intelligence | 4 — Emergent Intelligence |
| 4.7 | Law of Attention and Trajectory | 4 — Emergent Intelligence |
| 5.1 | TELOS Commitment | 5 — Commitment Theory |
