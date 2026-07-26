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
| 5.1 | TELOS Commitment (Unified) | `J = αU - βC_m - γC_r - δC_i - εC_align + ζG_theory + ηI_gain - θE_interpret + OP + CF - PE` — Unified Cognitive Functional extending commitment with information gain, theory gain, uncertainty bonus, alignment cost, interpretation energy, and identity violation cost | `CommitmentScore` in `commitment_optimizer.py` — 15-term optimization objective |

## Layer 6: Cognitive Dynamics (v2.5 — July 2026)
| # | Axiom | Meaning | Implementation |
|---|-------|---------|----------------|
| 6.1 | **Cognitive Potential** | An agent has measurable unused capacity Ψ_c = C_available − C_used; saturation indicates learning ceiling | `ResourceGradientTracker` tracks per-dimension utilization |
| 6.2 | **Cognitive Momentum** | Decisions carry inertia M_c = Σ w_i · a_i; high momentum → hard to change policy | `CognitiveMomentum` — `momentum`, `is_locked_in`, `recommend_unstick()` |
| 6.3 | **Interpretation Energy** | Axiom conflicts have computational cost E_I = D(P_i, P_j) · C; not free | `InterpretationEngine` estimates trade-offs and archives rationale |
| 6.4 | **Identity Compression** | Identity is a compressed function of history I = f(History); compression ratio ρ = |History|/|Identity| measures abstraction | `IdentityCompression` — `overall_compression_rate`, `get_identity_markers()` |
| 6.5 | **Theory Formation is a Computational Process** | Intelligence creates theories: Experience → Pattern → Hypothesis → Test → Theory | `TheoryBuilder` + `TheoryStream` — formal abstraction pipeline as first-class stream |
| 6.6 | **Knowledge is Compressed Experience** | Knowledge is not accumulated data; it is compressed structure extracted from repeated experience | `TheoryBuilder` clusters, `IdentityCompression` compresses, `ExplanationCompression` distills rules |
| 6.7 | **Intelligence is Recursive** | Intelligent systems construct models of themselves, their environment, and other systems simultaneously | `SystemSelf` (self-model), `TheoryBuilder` (world-model), `RelationalContext` (other-agent scaffold) |
| 6.8 | **Curiosity is a Gradient** | Curiosity climbs ∇U_knowledge — the steepest expected information gain, not just novelty | `CuriosityDrive` computes learning rate; `UnknownUnknownDetector` finds blind spots |

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
| 6.1 | Cognitive Potential | 6 — Cognitive Dynamics |
| 6.2 | Cognitive Momentum | 6 — Cognitive Dynamics |
| 6.3 | Interpretation Energy | 6 — Cognitive Dynamics |
| 6.4 | Identity Compression | 6 — Cognitive Dynamics |
| 6.5 | Theory Formation | 6 — Cognitive Dynamics |
| 6.6 | Knowledge is Compressed Experience | 6 — Cognitive Dynamics |
| 6.7 | Intelligence is Recursive | 6 — Cognitive Dynamics |
| 6.8 | Curiosity is a Gradient | 6 — Cognitive Dynamics |


---

## Telos v2/v2.5 — Architectural Extensions (July 2026)

*Based on Prateek's architectural feedback — 9 new subsystems + 10 more in v2.5.*

| # | Component | Insight | Status | File |
|---|-----------|---------|--------|------|
| 2.6 | **CouncilReflector** | Council must learn — "was that right?" meta-learning | ✅ Implemented | `core/council/reflector.py` |
| 2.7 | **ErrorAttributionEngine** | Not "I failed" but "which subsystem caused it?" | ✅ Implemented | `core/meta/error_attribution.py` |
| 3.6 | **AssumptionAuditor** | Curiosity questions assumptions, not just unknowns | ✅ Implemented | `core/curiosity/assumption_auditor.py` |
| 4.8 | **IdentityUtilityEngine** | Identity changes utility functions, not thresholds | ✅ Implemented | `core/identity/utility_profiles.py` |
| 1.4 | **IntrospectionScheduler** | Multi-timescale: act/100/1000 introspection | ✅ Implemented | `core/introspection/scheduler.py` |
| 2.8 | **RegretMemory** | Counterfactual what-if archival with retroactive evaluation | ✅ Implemented | `core/memory/regret_memory.py` |
| 2.9 | **TheoryBuilder** | Experience → cluster → hypothesis → test → theory | ✅ Implemented | `core/reasoning/theory_builder.py` |
| 5.2 | **AxiomEvolutionEngine** | System proposes axioms, human approves | ✅ Implemented | `core/axioms/evolution.py` |
| 4.9 | **InterpretationEngine** | Principle conflict → explanation → trade-off → archive | ✅ Implemented | `core/reasoning/interpretation_engine.py` |
| 6.1 | **CognitiveMomentum** | Decision inertia tracker M_c = Σ w_i · a_i | ✅ Implemented | `core/decision/cognitive_momentum.py` |
| 6.2 | **UnknownUnknownDetector** | Blind spot detection via residual classification | ✅ Implemented | `core/curiosity/unknown_unknown_detector.py` |
| 6.5 | **TheoryStream** | TheoryBuilder as first-class cognitive stream | ✅ Implemented | `core/streams/implementations.py` |

**Legend**: ✅ Implemented and wired into pipeline

### Layer Mapping
- **Layer 1** (Architectural): IntrospectionScheduler extends architectural awareness with multi-timescale reflection
- **Layer 2** (Feedback & Memory): CouncilReflector, ErrorAttributionEngine, RegretMemory, TheoryBuilder add feedback, attribution, memory, and abstraction
- **Layer 3** (Adaptive): AssumptionAuditor extends curiosity from exploration to assumption-challenging
- **Layer 4** (Emergent): IdentityUtilityEngine, InterpretationEngine add identity-driven utility and conflict resolution
- **Layer 5** (Commitment): AxiomEvolutionEngine enables meta-axiomatic growth
- **Layer 6** (Cognitive Dynamics): CognitiveMomentum, UnknownUnknownDetector, TheoryStream add decision inertia, blind-spot detection, and theory formation as core streams
