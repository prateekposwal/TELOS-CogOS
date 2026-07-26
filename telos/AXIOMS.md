# TELOS — 42 Axioms of Systemic Intelligence (v2.0)

## Layer 1: Architectural Invariance
| # | Axiom | Formal | Meaning | Implementation |
|---|-------|--------|---------|----------------|
| 1.1 | Architecture Produces Outcomes | — | The pipeline is a pure structural engine; outputs determined by architecture, not heuristics | `runtime.py` — 7-phase pipeline |
| 1.2 | Process over Outcomes | — | DecisionTrace captures integrity, not just results | `DecisionTrace` — DI, MD, council signals |
| 1.3 | Multi-Level Governance | — | TrustManager authorizes streams at mission context level | `trust_manager.py` — `authorize_knowledge_release()` |
| 1.4 | **Computational Conservation** | ΣR_i ≤ R_max | Every cognitive process consumes finite computational resources; sum of all resource usage is bounded | `BudgetManager` caps per-cycle compute; `ResourceGradientTracker` tracks per-dimension utilization |

## Layer 2: Feedback & Memory
| # | Axiom | Formal | Meaning | Implementation |
|---|-------|--------|---------|----------------|
| 2.1 | Governance First | — | ReadinessEngine and ConstraintValidator check before action | `timing.py`, `validators.py` — `InformationReadinessEngine` |
| 2.2 | Feedback Loops | — | InfraManager observes results and adjusts parameters | `infrastructure_manager.py` — `observe()` → calibration |
| 2.3 | Kintsugi | — | Failures are recorded as structural assets, not discarded | `failure_ledger.py` — `FailureRecord` + root-cause tracking |
| 2.4 | Path Dependency | — | All decision functions are history-aware | `world_ledger.py`, `planning_horizon.py` |
| 2.5 | Delayed Causality | — | Adaptive horizon adjusts simulation depth based on stability | `infrastructure_manager.py` — `adaptive_horizon` |
| 2.6 | **Reflection Is Episodic** | τ_reflect > τ_decision | Reflection operates on a slower timescale than action; structurally separated as post-action phase | `ReflectPhase` runs after Act; `IntrospectionScheduler` provides cycle/100/1000 cadence |
| 2.7 | **Meta-Error Attribution** | Error → Subsystem → Update | Every failure identifies the subsystem responsible, enabling targeted correction | `ErrorAttributionEngine` — subsystem-level attribution with health tracking |

## Layer 3: Adaptive Capacity
| # | Axiom | Formal | Meaning | Implementation |
|---|-------|--------|---------|----------------|
| 3.1 | Maintenance vs Recovery | M_t > M_min before E_{t+1} | System preserves integrity before increasing capability; recovery mode tightens policy on failure | `infrastructure_manager.py` — `enter_recovery()`/`exit_recovery()` |
| 3.2 | State Maintenance | — | BudgetManager reserves slices for lower-priority streams | `attention.py` — `reserve()`/`check_budget()` |
| 3.3 | Option Decay | — | Skills not matched within prune_age_cycles are archived | `skill_library.py` — `prune()` |
| 3.4 | Exploration vs Exploitation | — | UCB + Thompson sampling for domain exploration | `mission_policy.py` — `exploration_bonus()`, `thompson_sample()` |
| 3.5 | Structural Inertia | — | Non-selected streams get influence boost to compete | `stream_calibrator.py` — `influence_weight *= 1.08` on non-selection |
| 3.6 | **Curiosity Seeks Broken Models** | C = αN + βS + γPE | Curiosity is driven by novelty, surprise, and prediction error; the system seeks situations where its model is wrong | `UnknownUnknownDetector` finds blind spots; `CuriosityDrive` rewards learning rate; `AssumptionAuditor` questions held beliefs |

## Layer 4: Emergent Intelligence
| # | Axiom | Formal | Meaning | Implementation |
|---|-------|--------|---------|----------------|
| 4.1 | Identity Shapes Decisions | I_{t+1} = I_t + ΔI_t, |ΔI_t| ≤ ε | Identity is maintained through continuous structural consistency; SemanticDepth 4-layer ladder; bounded updates | `system_self.py` — ψ operator; `world_ledger.py` — SemanticDepth |
| 4.2 | Exploration/Comfort Trade-off | — | System balances known-safe vs novel actions | `mission_policy.py` — risk/exploration params |
| 4.3 | Possibility Preservation | — | CounterfactualEngine always generates alternatives | `simulation.py` — |F_t| ≥ 1 |
| 4.4 | Structural Resilience | — | DecisionFirewall provides pre-execution reality audit | `firewall.py` — `inspect()` |
| 4.5 | Local vs Global Optima | — | StreamCalibrator detects dominant-stream lock-in | `stream_calibrator.py` — `is_stuck()`, `forced_exploration_stream()` |
| 4.6 | Emergent Intelligence | — | No single stream is "I"; coordination = intelligence | `synthesize.py` — `SynthesisPhase` merges intents |
| 4.7 | Law of Attention and Trajectory | — | Attention allocation → counterfactual generation → trajectory shape | `core/attention/projection.py` |
| 4.8 | **Models Compete** | ΣP(M_i) = 1 | Multiple explanations coexist until evidence resolves uncertainty; no model is ever fully killed | `ModelCompetition` — Bayesian posterior updates, probability normalization |
| 4.9 | **Relational Optimization** | A_i = (U_i, Θ_i) | Other agents are modeled as optimizers with utility functions and internal parameters | `RelationalContext` (scaffold) — trust/authority/collaboration fields |
| 4.10 | **Recursive World Models** | M_A(B), M_A(M_B(A)), depth ≤ 3 | Agents recursively model one another's models, bounded at third order | `SystemSelf` (self-model), `TheoryBuilder` (world-model), `RelationalContext` (other-model scaffold) |
| 4.11 | **Cooperative Intelligence** | U_group > ΣU_i − C_align | Collective optimization exceeds isolated optimization whenever alignment costs are sufficiently low | (long-term — multi-agent architecture required) |

## Layer 5: Commitment Theory
| # | Axiom | Formal | Meaning | Implementation |
|---|-------|--------|---------|----------------|
| 5.1 | **TELOS Commitment (Unified Cognitive Functional)** | J(τ) = αU − βC_m − γC_r − δC_i − εC_align + ζG_theory + ηI_gain − θE_interpret + OP + CF − PE − C_o | Every decision optimizes the Unified Cognitive Functional: utility minus maintenance/recovery/identity/alignment/opportunity costs plus theory/information/uncertainty gains minus interpretation/conflict energy | `CommitmentScore` in `commitment_optimizer.py` — 16-term optimization objective evaluated every cycle |
| 5.2 | **Axiom Evolution** | A → Proposal → Human → Update | Axioms are not self-modified; they generate candidate revisions for human approval | `AxiomEvolutionEngine` — observes cycles, formulates proposals, routes through HumanGateway |
| 5.3 | **Identity Coupling** | C_align = λD(I_A, I_B) | Interaction cost between agents depends on identity divergence; alignment cost scales with distance | `CommitmentScore.alignment_cost` (constitutional); inter-agent coupling requires multi-agent (see 4.11) |

## Layer 6: Cognitive Dynamics (v2.5 — July 2026)
| # | Axiom | Formal | Meaning | Implementation |
|---|-------|--------|---------|----------------|
| 6.1 | **Cognitive Potential** | Ψ_c = C_available − C_used | An agent has measurable unused capacity; saturation indicates learning ceiling | `ResourceGradientTracker` tracks per-dimension utilization |
| 6.2 | **Cognitive Momentum** | M_c = Σ w_i · a_i | Decisions carry inertia; high momentum → hard to change policy | `CognitiveMomentum` — `momentum`, `is_locked_in`, `recommend_unstick()` |
| 6.3 | **Interpretation Energy** | E_I = D(P_i, P_j) · C | Axiom conflicts have computational cost; interpretation is not free | `InterpretationEngine` estimates trade-offs and archives rationale |
| 6.4 | **Identity Compression** | I = Φ(E_{1:n}), ρ = |History| / |Identity| | Identity is the compressed representation of accumulated experience; higher ratio = more abstraction | `IdentityCompression` — `overall_compression_rate`, `get_identity_markers()` |
| 6.5 | **Theory Formation** | Experience → Pattern → Hypothesis → Test → Theory | Experience is continuously abstracted into reusable theories via a formal abstraction pipeline | `TheoryBuilder` + `TheoryStream` — first-class cognitive stream |
| 6.6 | **Every Theory Remains Revisable** | P(T|E) ∝ P(E|T)P(T) | No internal model is permanently correct; confidence evolves with evidence via Bayesian revision | `ModelCompetition` maintains P(M|E); TheoryBuilder tests and falsifies hypotheses |
| 6.7 | **Knowledge is Compressed Experience** | — | Knowledge is not accumulated data; it is compressed structure extracted from repeated experience | `ExplanationCompression` distills rules; `IdentityCompression` abstracts principles |
| 6.8 | **Intelligence is Recursive** | M_A(B), M_A(M_B(A)) | Intelligent systems construct models of themselves, their environment, and other systems simultaneously | `SystemSelf`, `TheoryBuilder`, `RelationalContext` |
| 6.9 | **Curiosity is a Gradient** | ∇U_knowledge | Curiosity climbs the steepest expected information gain, not just novelty | `CuriosityDrive` computes learning rate; `UnknownUnknownDetector` finds blind spots |
| 6.10 | **Unknown Unknown Discovery** | R_u = f(PE, Novelty) | The system allocates resources to unexplained residuals; prediction error in novel contexts signals missing concepts | `UnknownUnknownDetector` — residual classification, novelty clustering, question formation |
| 6.11 | **Opportunity Cost Exists** | C_o = max(U_i) − U_chosen | Every action carries the value of abandoned alternatives; the best foregone option is an explicit cost | `CommitmentScore.opportunity_cost` — computed from intent ranking |

| # | Short Name | Layer |
|---|------------|-------|
| 1.1 | Architecture Produces Outcomes | 1 — Architectural |
| 1.2 | Process over Outcomes | 1 — Architectural |
| 1.3 | Multi-Level Governance | 1 — Architectural |
| 1.4 | Computational Conservation | 1 — Architectural |
| 2.1 | Governance First | 2 — Feedback |
| 2.2 | Feedback Loops | 2 — Feedback |
| 2.3 | Kintsugi | 2 — Feedback |
| 2.4 | Path Dependency | 2 — Feedback |
| 2.5 | Delayed Causality | 2 — Feedback |
| 2.6 | Reflection Is Episodic | 2 — Feedback |
| 2.7 | Meta-Error Attribution | 2 — Feedback |
| 3.1 | Maintenance vs Recovery | 3 — Adaptive |
| 3.2 | State Maintenance | 3 — Adaptive |
| 3.3 | Option Decay | 3 — Adaptive |
| 3.4 | Exploration vs Exploitation | 3 — Adaptive |
| 3.5 | Structural Inertia | 3 — Adaptive |
| 3.6 | Curiosity Seeks Broken Models | 3 — Adaptive |
| 4.1 | Identity Continuity | 4 — Emergent |
| 4.2 | Exploration/Comfort Trade-off | 4 — Emergent |
| 4.3 | Possibility Preservation | 4 — Emergent |
| 4.4 | Structural Resilience | 4 — Emergent |
| 4.5 | Local vs Global Optima | 4 — Emergent |
| 4.6 | Emergent Intelligence | 4 — Emergent |
| 4.7 | Law of Attention | 4 — Emergent |
| 4.8 | Models Compete | 4 — Emergent |
| 4.9 | Relational Optimization | 4 — Emergent (scaffold) |
| 4.10 | Recursive World Models | 4 — Emergent (scaffold) |
| 4.11 | Cooperative Intelligence | 4 — Emergent (aspirational) |
| 5.1 | TELOS Commitment (Unified J) | 5 — Commitment |
| 5.2 | Axiom Evolution | 5 — Commitment |
| 5.3 | Identity Coupling | 5 — Commitment |
| 6.1 | Cognitive Potential | 6 — Cognitive Dynamics |
| 6.2 | Cognitive Momentum | 6 — Cognitive Dynamics |
| 6.3 | Interpretation Energy | 6 — Cognitive Dynamics |
| 6.4 | Identity Compression | 6 — Cognitive Dynamics |
| 6.5 | Theory Formation | 6 — Cognitive Dynamics |
| 6.6 | Theory Revisability | 6 — Cognitive Dynamics |
| 6.7 | Knowledge Compression | 6 — Cognitive Dynamics |
| 6.8 | Recursive Intelligence | 6 — Cognitive Dynamics |
| 6.9 | Curiosity Gradient | 6 — Cognitive Dynamics |
| 6.10 | Unknown Unknown Discovery | 6 — Cognitive Dynamics |
| 6.11 | Opportunity Cost | 6 — Cognitive Dynamics |


---

## Telos v2/v2.5 — Extension Modules (July 2026)

| Module | Axiom | Insight | Status | File |
|--------|-------|---------|--------|------|
| CouncilReflector | 2.2 | Council must learn — "was that right?" meta-learning | ✅ | `core/council/reflector.py` |
| ErrorAttributionEngine | 2.7 | Not "I failed" but "which subsystem caused it?" | ✅ | `core/meta/error_attribution.py` |
| AssumptionAuditor | 3.6 | Curiosity questions assumptions, not just unknowns | ✅ | `core/curiosity/assumption_auditor.py` |
| IdentityUtilityEngine | 5.3 | Identity changes utility functions, not thresholds | ✅ | `core/identity/utility_profiles.py` |
| IntrospectionScheduler | 2.6 | Multi-timescale: act/100/1000 introspection | ✅ | `core/introspection/scheduler.py` |
| RegretMemory | 6.11 | Counterfactual what-if archival with retroactive evaluation | ✅ | `core/memory/regret_memory.py` |
| TheoryBuilder | 6.5 | Experience → cluster → hypothesis → test → theory | ✅ | `core/reasoning/theory_builder.py` |
| AxiomEvolutionEngine | 5.2 | System proposes axioms, human approves | ✅ | `core/axioms/evolution.py` |
| InterpretationEngine | 6.3 | Principle conflict → explanation → trade-off → archive | ✅ | `core/reasoning/interpretation_engine.py` |
| CognitiveMomentum | 6.2 | Decision inertia tracker M_c = Σ w_i · a_i | ✅ | `core/decision/cognitive_momentum.py` |
| UnknownUnknownDetector | 6.10 | Blind spot detection via residual classification | ✅ | `core/curiosity/unknown_unknown_detector.py` |
| TheoryStream | 6.5 | TheoryBuilder as first-class cognitive stream | ✅ | `core/streams/implementations.py` |
| ModelCompetition | 4.8 | Bayesian hypothesis competition | ✅ | `core/reasoning/model_competition.py` |
| RelationalContext | 4.9, 4.10 | Multi-agent reasoning scaffold | 📄 Scaffold | `core/reasoning/relational.py` |
| HumanGateway | 5.2 | Human-in-the-loop for axiom proposals + escalation | ✅ | `core/governance/human_gateway.py` |
