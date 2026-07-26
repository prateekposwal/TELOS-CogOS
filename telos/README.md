# TELOS — A Cognitive Operating System

> *"An intelligent system is defined not by the number of visible capabilities it possesses, but by the invisible coordination of latent cognitive processes working toward a unified mission."*
>
> — The Principle of Latent Cognition (Axiom 4.6)

---

## Part I: The Laws of Systemic Intelligence

TELOS is not a model, an agent, or a framework. It is a **Cognitive Operating System (CogOS)** — a formally axiomatized system for constructing intelligent behavior from first principles. The following twenty axioms constitute the **Constitution of TELOS**. Every component in this codebase exists to satisfy one or more of these axioms. If a component violates them, it is a bug — even if the code executes without error.

These axioms are organized into four architectural layers, each representing a distinct dimension of systemic intelligence.

---

### Layer 1: Foundational Axioms (The Nature of Intelligence)

| # | Axiom | Design Constraint | Implementation |
|---|-------|-------------------|----------------|
| 1.1 | **Architecture Produces Outcomes** | Logic must be verifiable through the system's structure, not its training data. | `telos/core/runtime.py` — the Pipeline is a pure structural engine; outcomes follow from coordination topology, not learned weights |
| 1.2 | **Process over Outcomes** | The runtime must optimize the *decision trajectory*, not the instantaneous result. | `DecisionTrace` captures multi-cycle trajectory; `PipelineResult` includes `decision_integrity` (DI) as a trajectory-quality metric |
| 1.3 | **Multi-Level Architecture** | System, Identity, Policy, and Action must be decoupled and independently optimizable. | `core/runtime.py` (System), `core/ledger/world_ledger.py` (Identity), `core/infra_manager/mission_policy.py` (Policy), `contracts/domain_model.py` (Action) |

### Layer 2: Dynamics Axioms (How Intelligence Evolves)

| # | Axiom | Design Constraint | Implementation |
|---|-------|-------------------|----------------|
| 2.1 | **Constraint Propagation** | A constraint at the root must mathematically limit the state-space of the decision manifold. | `DomainFacts.constraints` flow through governance into `DecisionFirewall`; a root constraint (`_bounds`) propagates to block actions violating safety |
| 2.2 | **Feedback Loops** | State changes must recursively reinforce or correct the underlying identity/policy. | `InfrastructureManager` observes `PipelineResult` and adjusts risk tolerance and exploration budget from failure trends |
| 2.3 | **Compounding Systems (Kintsugi)** | Every decision must include a "learning interest" added to the ledger. | `FailureLedger` records every failure as structural knowledge; `MemoryAdvisor` queries the ledger to block actions matching past failure patterns |
| 2.4 | **Path Dependency (Hysteresis)** | All decision functions must be history-aware. | `WorldLedger` accumulates `EntityRecord` with observation timelines; `RepresentationPlanner` logs selection history; both influence future decisions |
| 2.5 | **Delayed Causality** | Optimization horizons must exceed the lag between decision and environment feedback. | `PipelineConfig.feedback_lag` configures expected lag; `execute()` uses `effective_horizon = max(horizon, feedback_lag + 1)`; `CounterfactualEngine` simulates that many steps ahead |

### Layer 3: Lifecycle Axioms (System Health & Survival)

| # | Axiom | Design Constraint | Implementation |
|---|-------|-------------------|----------------|
| 3.1 | **Maintenance vs. Recovery** | System health must be measurable; recovery must be triggered *before* failure states. | `AuditController` computes a composite `health_score` from DI trend, failure rate, and governance block rate; `InfrastructureManager` auto-enters recovery mode when `≥3 failures in 10 cycles`; external monitors can subscribe via `on_recovery_event(callback)` |
| 3.2 | **State Maintenance** | The World model must actively preserve state energy (computational budget). | `BudgetManager` enforces a per-cycle compute budget; streams exceeding budget are silently skipped — budget *is* the attention mechanism |
| 3.3 | **Option Decay** | Unused simulation trajectories must be pruned or archived to save entropy. | `SkillLibrary.prune()` archives skills not matched in `prune_age_cycles`; `reset_cycle()` restores archived skills (zero information loss); `MemoryAdvisor` reports weak matches as dissent |
| 3.4 | **Adaptive Capacity** | The runtime must be able to reset or recover its architecture without losing its mission. | `MissionPolicy` stores the current mission; `InfrastructureManager` can adjust parameters in-place without pipeline reconstruction |
| 3.5 | **Structural Inertia** | Changes to core infrastructure must be logged and require state-change confirmation. | `MissionPolicyManager` logs all policy changes; `MissionDriftDetector` tracks cumulative predicted-vs-observed divergence across cycles |

### Layer 4: Intelligence Axioms (What It Means to Think)

| # | Axiom | Design Constraint | Implementation |
|---|-------|-------------------|----------------|
| 4.1 | **Identity Shapes Decisions** | The system's internal self-model must be an explicit variable in the decision function. | `SemanticDepth` (4-layer ladder: Observable → Historical → Mission → Identity) is the system's self-model; `WorldLedger.enrich()` synthesizes it each cycle |
| 4.2 | **Exploration vs. Comfort** | The runtime must have a tunable "Exploration Temperature" that increases under staleness. | `MissionPolicy.exploration_budget` controls the fraction of compute allocated to the `PlanningStream`; `InfrastructureManager` increases it after stable low-drift periods |
| 4.3 | **Possibility Preservation** | The system must always maintain a set of alternative future trajectories. | `CounterfactualEngine.generate_worlds()` produces `n_worlds` alternative futures; unused trajectories remain available for `StrategicOption` queries |
| 4.4 | **Structural Resilience** | The system must minimize Identity Entropy to prevent collapse under stress. | `Council` blocks actions with low DI or high MD before they execute; `DecisionFirewall` provides a second governance gate; blocked decisions are cheaper than failed actions |
| 4.5 | **Local vs. Global Optima** | Every module must report its local optimization to prevent Global Mission Drift. | `CouncilVerdict` includes `mission_drift` (MD) metric aggregated from individual validator signals; `MissionDriftDetector` compares predicted vs. observed divergence |
| 4.6 | **Emergent Intelligence (Latent Cognition)** | Intelligence is the aggregate of all streams; no single stream holds the "I." | Multiple `CognitiveStream`s coordinate via the `Pipeline`; the `TransparencyMonitor` exposes each stream's contribution; intelligence = coordination, not capability |
| 4.7 | **Law of Attention and Trajectory** | Past failure states must be stored as structural barriers in the World Model. | `FailureLedger` records root causes; `WorldLedger` records entity history; `MemoryAdvisor` queries `SkillLibrary` for historical contradictions — past failures become structural barriers |
| 4.8 | **Structural Inertia (Logging)** | Changes to core infrastructure must be logged and require a state-change confirmation. (Reinforced — see 3.5) | Every `MissionPolicy` change is recorded; the `TransparencyMonitor` logs every cycle; infrastructure changes are always observable |

---

## Part II: Architecture Overview

The TELOS runtime is a **pure reasoning pipeline** governed by the axioms above. It executes one decision cycle per invocation, producing a `DecisionTrace` that serves as the formal proof of axiom satisfaction.

```
┌─────────────────────────────────────────────────────────────────┐
│                      INFRASTRUCTURE MANAGER                      │
│              (Meta-Runtime — Axioms 2.2, 2.3, 3.1, 3.4)         │
│   StreamCalibrator · FailureLedger · MissionPolicy · Audit      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────┐  ┌───────────┐  ┌───────────┐  ┌────────────┐   │
│   │  Reflex  │  │Perception │  │  Memory   │  │  Planning  │   │
│   │  Stream  │  │  Stream   │  │  Stream   │  │  Stream    │   │
│   │  (1.0)   │  │  (0.9)    │  │  (0.7)    │  │  (0.5)    │   │
│   └────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬──────┘   │
│        │               │              │               │         │
│        └───────────────┴──────┬───────┴───────────────┘         │
│                               │                                  │
│                  ┌────────────▼────────────┐                     │
│                  │    Budget Manager        │                    │
│                  │  (Axiom 3.2: State Maint.)│                   │
│                  └────────────┬────────────┘                     │
│                               │                                  │
│                  ┌────────────▼────────────┐                     │
│                  │ Representation Planner   │                    │
│                  │  (Axiom 4.2: Explor/Comf)│                   │
│                  └────────────┬────────────┘                     │
│                               │                                  │
│                  ┌────────────▼────────────┐                     │
│                  │ Counterfactual Engine    │                    │
│                  │  (Axioms 2.5, 4.3)      │                    │
│                  └────────────┬────────────┘                     │
│                               │                                  │
├───────────────────────────────▼──────────────────────────────────┤
│              COUNCIL OF COGNITIVE ADVISORS                       │
│  (Axioms 2.1, 4.4, 4.5 — Blocking Epistemic Integrity Check)    │
│   Reality · Constraint · MemoryAdvisor · MissionDriftDetector    │
├───────────────────────────────▼──────────────────────────────────┤
│                    DECISION FIREWALL                              │
│        (Axiom 4.4 — Final Governance Gate)                       │
├───────────────────────────────▼──────────────────────────────────┤
│                      GOVERNANCE LAYER                             │
│       TrustManager · ReadinessEngine (Axiom 2.1)                 │
├─────────────────────────────────────────────────────────────────┤
│                  SHARED WORLD MODEL + LEDGER                      │
│     (Axioms 2.4, 4.1, 4.7 — Path Dependency + Identity)          │
├─────────────────────────────────────────────────────────────────┤
│                  TRANSPARENCY MONITOR                             │
│     (Axioms 1.2, 4.6 — Empirical Proof of Latent Cognition)      │
└─────────────────────────────────────────────────────────────────┘
```

### Pipeline Phases

A single decision cycle executes seven phases, each satisfying specific axioms:

```
PERCEIVE → STREAMS → SIMULATE → EVALUATE → SELECT → COUNCIL → ACT → REFLECT
```

| Phase | Axioms Satisfied | Description |
|-------|------------------|-------------|
| PERCEIVE | 2.4, 4.1, 4.7 | Ingest raw state → build World → extract DomainFacts → enrich with ledger history |
| STREAMS | 3.2, 4.2, 4.6 | Each CognitiveStream processes World within budget; influence-weighted by StreamCalibrator (Axiom 2.2) |
| SIMULATE | 2.5, 4.3 | CounterfactualEngine generates alternative futures (Possibility Preservation) |
| EVALUATE | 1.2, 4.5 | Intents ranked by utility + influence weight; representation selected (Local vs. Global Optima) |
| SELECT | 1.2, 4.6 | Best intent chosen; trajectory optimized (Process over Outcomes) |
| COUNCIL | 2.1, 4.4, 4.5 | Validators check reality, constraints, history, mission drift — BLOCKING (Structural Resilience) |
| ACT | 1.1, 1.3 | Intent → action via adapter (Architecture Produces Outcomes, Multi-Level) |

---

## Part III: Key Components


## Part IIIb: v2/v2.5 Modules

19 architectural modules supplement the core pipeline with meta-cognition, curiosity, regret, debate, and identity compression. Each runs at a specific phase hook:

| Module | Phase Hook | Purpose |
|--------|-----------|---------|
| `UnknownUnknownDetector` | Post-Perceive | Finds blind spots — what the system should know but hasn't considered |
| `ModelCompetition` | Post-Evaluate | Bayesian competition between multiple hypotheses |
| `InternalDebate` | Post-Select | Multi-perspective deliberation (optimist, skeptic, economist, engineer, ethicist) |
| `CouncilReflector` | Post-Council | Meta-learning — evaluates council accuracy after outcomes |
| `TheoryBuilder` | Post-Act | Experience → cluster → hypothesis → theory pipeline |
| `RegretMemory` | Post-Act | Counterfactual what-if archival for future planning |
| `AxiomProver` | Post-Council | Verifies all 20 axioms against the decision trace |
| `SurpriseBudget` | Post-cycle | Prediction error drives compute allocation |
| `CognitiveEnergy` | Post-cycle | Mental fatigue model — depletes on hard decisions |
| `DualConfidence` | Post-cycle | Separates decision confidence from explanation confidence |
| `TimeHorizonSeparator` | Post-cycle | Four-horizon utility (immediate/short/long/irreversible) |
| `IdentityCompression` | Post-cycle | Batches experiences into identity markers |
| `ExplanationCompression` | Post-cycle | Finds minimal rules from outcome patterns |
| `IdentityUtilityEngine` | Post-cycle | Identity-modulated utility function selection |
| `AssumptionAuditor` | Post-cycle | Periodic assumption challenges |
| `ActiveForgetting` | Post-cycle | Deliberate belief examination and pruning |
| `IntrospectionScheduler` | Post-cycle | 3-tier reflection (cycle/reflect/strategic) |
| `ErrorAttributionEngine` | Post-cycle | Subsystem-level error attribution |
| `AxiomEvolutionEngine` | Post-cycle | System proposes new axioms, human approves |

### Knowledge & Inference (`telos/core/knowledge/`)
Powered by `KGInferenceEngine`, providing Euclidean similarity for knowledge retrieval and clustering of failure patterns for structural memory enhancement (Axiom 3.3).

### Planning Horizon (`telos/core/planning_horizon.py`)
State machine for persistent sequence of `IntentIR` tasks. Supports plan deferral and stateful persistence (Axiom 2.4).

### Cognitive Streams (`telos/core/streams/`)
Four specialized processes, processed in priority order. Axiom 4.6 (Emergent Intelligence): no single stream holds the "I."

| Stream | Priority | Axioms | Function |
|--------|----------|--------|----------|
| `ReflexStream` | 1.0 | 4.4 | Fast reactivity — detects safety violations, high uncertainty, terminal states |
| `PerceptionStream` | 0.9 | 4.1 | Feature extraction — transforms raw state into semantic entities and affordances |
| `MemoryStream` | 0.7 | 4.7 | Procedural memory — queries SkillLibrary for relevant past trajectories |
| `PlanningStream` | 0.5 | 2.5, 4.3 | Deep simulation — generates counterfactual futures via CounterfactualEngine |

### Council of Cognitive Advisors (`telos/core/council/`)
Blocking epistemic integrity check. Axiom 4.5 (Local vs. Global Optima): each validator reports local optimization; the aggregated verdict includes global Mission Drift.

- **RealityValidator** — NaN/Inf detection, action-vector integrity
- **ConstraintValidator** — Safety threshold, constraint propagation (Axiom 2.1)
- **MemoryAdvisor** — Historical contradiction detection via SkillLibrary (Axiom 4.7)
- **MissionDriftDetector** — Predicted-vs-observed divergence with cumulative tracking (Axioms 3.5, 4.5)

### Governance Layer (`telos/core/governance/`)
Three components enforcing Cognitive Confidentiality:

- **TrustManager** — Stream authorization against mission context (Axiom 1.3: Multi-Level)
- **InformationReadinessEngine** — Fact lifecycle (LOCKED → PENDING → READY → EXPIRED); prevents premature access to immature information (Axiom 2.5: Delayed Causality)
- **DecisionFirewall** — Pre-execution reality audit; checks council validation, DI threshold, mission violation (Axiom 4.4: Structural Resilience)

### Infrastructure Manager (`telos/core/infra_manager/`)
The Meta-Runtime. Observes PipelineResult and adjusts system parameters. This is the self-modifying loop (Axiom 2.2: Feedback Loops).

- **StreamCalibrator** — Evidence-weighted influence tracking; reduces weight of high-drift streams
- **FailureLedger** — Kintsugi failure recording (Axiom 2.3: Compounding Systems)
- **MissionPolicyManager** — Risk/exploration/ambition parameters; adaptive adjustment from failure trends (Axiom 3.4: Adaptive Capacity)
- **AuditController** — Infrastructure health monitoring; generates composite health score (Axiom 3.1: Maintenance vs. Recovery)
- **Recovery Mode** — Auto-enters when `≥3 failures in 10 cycles`; tightens all 4 policy parameters; exits after 5 clean cycles. External monitors react via `on_recovery_event(callback)`

### World Ledger (`telos/core/ledger/world_ledger.py`)
History-aware entity persistence. Axiom 2.4 (Path Dependency): all decision functions are history-aware. Axiom 4.1 (Identity Shapes Decisions): Semantic Depth ladder provides the system's self-model.

```
Entity Record:
  Observable State ──→ Historical Context ──→ Mission Context ──→ Semantic Identity
  (cycle n facts)      ("newly_discovered"     (relevance to        (e.g., "active_region
                         → "well_known_3")       current mission")     _persistent_entity")
```

### Transparency Monitor (`telos/audit/monitor.py`)
Empirical proof of the Systemic Axioms. Generates `decision_log.json` (machine-readable) and `transparency_report.md` (human-readable). Every cycle's trace proves the axioms were satisfied — or records exactly which one was violated.

---

## Part IV: Code Review Criteria

Before merging any change to `telos/core/`, the system must answer:

| Axiom | Review Question |
|-------|-----------------|
| 2.4 | Does this violate **Path Dependency**? Are we accidentally deleting history? |
| 3.3 | Does this allow for **Option Decay**? Are we retaining unused trajectories? |
| 3.1 | Does this support **Recovery Cost** analysis? Does this change make the system harder to recover? |
| 2.1 | Does this **Constraint Propagation** properly? Can a root constraint still limit the decision manifold? |
| 4.1 | Does this preserve **Identity** as an explicit variable? Can the system still answer "who am I?" |
| 4.6 | Does this concentrate authority in a single stream? Is any single component the "I"? |
| 3.5 | Is this change **logged**? Could we roll it back from the audit log? |

---

## Part V: Running

```python
from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.simulation import CounterfactualEngine
from telos.core.streams.implementations import ReflexStream, PerceptionStream, MemoryStream, PlanningStream
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.council.validators import RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector
import numpy as np

sim = MyDomainSimulator()
config = PipelineConfig(simulator=sim, compute_budget_ms=100.0, state_dim=6)
pipeline = TelosV14Pipeline(config)
skill_lib = SkillLibrary()
sim_engine = CounterfactualEngine(sim)

pipeline.register_stream(ReflexStream(skill_lib))
pipeline.register_stream(PerceptionStream(skill_lib))
pipeline.register_stream(MemoryStream(skill_lib))
pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))

pipeline.register_validator(RealityValidator())
pipeline.register_validator(ConstraintValidator())
pipeline.register_validator(MemoryAdvisor(skill_lib))
pipeline.register_validator(MissionDriftDetector())

state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
result = pipeline.execute(state)

trace = result.decision_trace
print(f"Health: {result.health_score:.3f}")
print(f"DI: {trace.decision_integrity:.3f}, MD: {trace.mission_drift:.3f}")
print(f"Streams activated: {len([a for a in trace.stream_activations if a.activated])}")
```

---

## Part VI: Testing

```bash
python3 -m pytest tests/
```

422 tests across 47 files covering all 20 axioms, the Pipeline, Council, Governance, WorldLedger, InfrastructureManager, Transparency Monitor, domain plugin compliance (DSI contract), StrategicOption queries, architectural invariance, all 19 v2/v2.5 modules, and the complete Unified Cognitive Functional J.

---

## License

Research use. See CONTRIBUTING.md for details.
