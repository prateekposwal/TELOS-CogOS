# TELOS — Theorems & Principles of Systemic Intelligence

> *"An intelligent system is defined not by the number of visible capabilities it possesses, but by the invisible coordination of latent cognitive processes working toward a unified mission."*
>
> *"An intelligent system is not defined by how confidently it pursues a mission, but by its ability to continuously expose, evaluate, and integrate inconvenient truths before acting."*

---

## Table of Contents
1. [The Four Pillars of Systemic Intelligence](#1-the-four-pillars-of-systemic-intelligence)
2. [The Law of Attention and Trajectory (Axiom 4.7)](#2-the-law-of-attention-and-trajectory-axiom-47)
3. [The 10 Security Defenses](#3-the-10-security-defenses)
4. [Data Flow Integrity Patterns (DFI-01 to DFI-05)](#4-data-flow-integrity-patterns-dfi-01-to-dfi-05)
5. [The Three-Layer Identity Model](#5-the-three-layer-identity-model)
6. [Store Boundary Normalization Principle](#6-store-boundary-normalization-principle)
7. [DI/MD Governance Metrics](#7-digovernance-metrics)

---

## 1. The Four Pillars of Systemic Intelligence

### 1.1 Infrastructure Manifesto
**"The system is measured by infrastructure health, not task accuracy."**

The TELOS evaluation framework (embodied in `AuditController`) evaluates the system by the maturity of its infrastructure components — not by domain-specific accuracy metrics. A system with perfect task accuracy but degraded infrastructure (stream calibrator stale, failure ledger overflowing, policy parameters drifting) is considered unhealthy. Conversely, a system with strong infrastructure metrics but currently suboptimal task performance is considered healthy and on a trajectory toward improvement.

**Implementation evidence:**
- `AuditController.generate_report()` computes composite health from DI trend, failure rate, governance block rate, and stream calibration coverage — not task accuracy
- `InfrastructureReport` contains zero domain-specific metrics
- Health score formula: `0.3 × avg_DI + 0.3 × (1 - failure_rate) + 0.2 × (1 - gov_block_rate) + 0.2 × avg_health`

### 1.2 Evidence-Weighted Influence
**"No stream has a priori authority — influence = Evidence × Confidence × Reliability."**

Cognitive streams do not possess inherent authority. Each stream must earn its influence through demonstrated reliability over time. The `StreamCalibrator` maintains per-stream calibrations and adjusts influence weights dynamically.

**Formula:**
```
Influence = evidence_score × mean_confidence × historical_reliability

Where:
  evidence_score = min(1.0, total_calls / 50)     [saturates at 50 observations]
  mean_confidence = mean(confidence_history[-20:])
  historical_reliability = accuracy × mean_confidence
```

**Implementation evidence:**
- `StreamCalibrator._recompute()` — three-term product with saturation
- `StreamCalibrator.get_evidence_weighted_influence()` — returns the full triplet
- Non-selected streams receive a 1.08× influence boost (Structural Inertia, Axiom 3.5) to prevent permanent lock-out

### 1.3 Kintsugi Ledger
**"Failures are structural assets — record → integrate into identity → repair."**

Borrowed from the Japanese art of golden joinery: a broken pot repaired with gold lacquer becomes stronger and more beautiful than the original. TELOS treats every failure as a structural asset. Failures are not errors to be discarded but insights to be integrated into the system's cognitive identity.

**Three-step cycle:**
1. **Record** — `FailureLedger` captures failure context: type, severity, root cause, blocked_by, decision_integrity, mission_drift
2. **Integrate into identity** — `FailureLedger.integrate_into_identity()` maps failure types to identity markers (e.g., `council_block` → `learning_governance`, `high_drift` → `calibrating_prediction`)
3. **Repair** — `InfrastructureManager._kintsugi_repair()` adjusts risk tolerance, shortens planning horizon, increases resilience

**Identity markers (failure type → marker mapping):**
| Failure Type | Identity Marker |
|---|---|
| council_block | `learning_governance` |
| firewall_block | `testing_boundaries` |
| high_drift | `calibrating_prediction` |
| low_integrity | `repairing_epistemics` |
| pattern_exploit | `breaking_patterns` |
| budget_starvation | `conserving_resources` |
| simulation_timeout | `improving_simulation` |
| escalation | `seeking_clarity` |

### 1.4 Confidence Adaptation
**"Uncertainty = std / sqrt(n) — streams earn authority through experience."**

Each stream's confidence in a given context is calibrated by repeated observation. The `ExperienceMap` maintains per-stream, per-context confidence distributions. A stream that has encountered a context 50 times speaks with higher certainty (lower uncertainty) than one encountering it for the first time.

**Formula:**
```
uncertainty = confidence_std / sqrt(n_observations)

Confidence update (online mean/std):
  μ_new = (μ_old × n + confidence) / (n + 1)
  σ_new² = (n × (σ_old² + (μ_old - μ_new)²) + (confidence - μ_new)²) / (n + 1)
```

**Implementation evidence:**
- `ExperienceEntry.uncertainty` — computed as `std / sqrt(n)`
- `ExperienceMap.update()` — online Welford-style update for mean and std
- `ExperienceMap.get_confidence()` — returns `(mean, uncertainty)` tuple

---

## 2. The Law of Attention and Trajectory (Axiom 4.7)

### Core Principle
**"Attention allocation → counterfactual generation → trajectory shape."**

The sustained allocation of attention determines which counterfactual futures are generated, which in turn shapes the trajectory of subsequent decisions. An agent fixated on threats will generate defensive worlds and pursue conservative trajectories. An agent exploring opportunities will generate diverse worlds and discover novel paths.

**Four measurable metrics:**

| Metric | Component | Meaning |
|--------|-----------|---------|
| Attention Allocation Ratio | `AttentionAllocation` | How budget splits across threat/opportunity/maintenance |
| Identity Entropy | `IdentityEntropyTracker` | Rolling action-space size |A_t| — high = many options, low = few |
| Counterfactual Diversity | `CounterfactualEngine.rolling_diversity` | Variance of simulated futures — bounds decision quality |
| Trajectory Divergence | `AttentionProjectionEngine` | ||predicted - actual|| — how simulation diverges from reality |

### Identity Entropy Dynamics
The action-space |A_t| expands and contracts under different cognitive states:
- **Threat-dominated cognition** (threat_ratio > 0.5) → |A_t| contracts → fewer options perceived → reactive/defensive choices dominate
- **Opportunity-dominated cognition** (opportunity_ratio > 0.5) → |A_t| expands → more counterfactuals generated → exploratory behavior
- **Identity collapse** (entropy < 40% of baseline + collapse_rate < -0.5) → the system is pathologically constricted. Immediate intervention required.

**Thresholds:**
- `COLLAPSE_THRESHOLD = -0.3` — rate below which action-space is contracting
- `CRITICAL_ENTROPY_FRACTION = 0.3` — fraction of baseline triggering alert
- `EXPANSION_THRESHOLD = 0.2` — rate above which action-space is growing

### Counterfactual Diversity
Decision quality is bounded by the variance of simulated futures:
- **High diversity** → system explores many trajectories → robust decisions
- **Low diversity** → system fixates on narrow set of futures → blind spots and brittle decisions
- Zero diversity indicates attention is pathologically locked-in

The `CounterfactualEngine` weights world generation by attention allocation:
- High threat_ratio → conservative, defensive trajectories (state clamped to [-2, 2])
- High opportunity_ratio → diverse exploration with perturbed initial states (noise = 0.2 × opp_ratio)
- High maintenance_ratio → status-quo-preserving, shorter-horizon trajectories

### Maintenance Cost vs Recovery Cost
Axiom 3.1 formalized as operational economics:
- **Maintenance costs**: resources spent on upkeep, calibration, prevention (DI > 0.8 cycles)
- **Recovery costs**: resources spent on fixing failures after they occur (failure cycles)
- `cost_efficiency = maintenance / recovery` — values > 1.0 mean proactive > reactive
- Trending: `healthy` (maintenance dominates), `critical` (recovery dominates), `deteriorating` (recovery rising)

### Trajectory Projection
The `AttentionProjectionEngine.project_trajectory()` predicts expected divergence given current attention policy:
```
expected_divergence = divergence_base × momentum_penalty × diversity_penalty × entropy_penalty × threat_penalty

Where:
  divergence_base = ||state|| × 0.1 + 0.1
  momentum_penalty = 1.0 + attention_momentum × 2.0
  diversity_penalty = 1.0 + max(0, 1.0 - diversity × 5.0)
  entropy_penalty = 1.0 + entropy_deficit × 2.0
  threat_penalty = 1.0 + mean_threat_ratio × 1.5
```

---

## 3. The 10 Security Defenses

TELOS implements 10 security defenses spanning governance, infrastructure, persistence, and identity. These are NOT access control lists — they are **structural defenses** against parameter drift, tampering, lock-in, and catastrophic state changes.

| # | Defense | Component | Mechanism |
|---|---------|-----------|-----------|
| 1 | **MutationGuard** | `InfrastructureManager` | Per-cycle rate limiter. Caps total delta per parameter (e.g., risk_tolerance max 0.05/cycle). Blocks runaway self-modification. |
| 2 | **ParameterBudget** | `MissionPolicyManager` | Cumulative drift tracking from genesis baseline. Max cumulative drift 0.5 per parameter. Prevents slow-burn attacks where small deltas compound over hundreds of cycles. |
| 3 | **DissentFloor** | `Council.evaluate()` | DI capped at 0.3 when any BLOCK exists. Prevents evidence-weight manipulation from silencing legitimate dissent. |
| 4 | **MaxCap** | `InfrastructureManager` + `StreamCalibrator` | Influence weight capped at 2.0. Parameter ranges clamped to [0.0, 1.0]. Action norms capped at 100. Prevents unbounded parameter growth. |
| 5 | **LRU+Hashing** | `ExperienceMap` | Bounded by MAX_ENTRIES=1000 with LRU eviction. Context keys hashed via SHA-256 (16-char digest). Prevents long-string DOS and memory exhaustion. |
| 6 | **MoodCooldown** | `SystemSelf` | Mood change allowed at most once per 20 cycles (`MOOD_CHANGE_COOLDOWN`). Prevents rapid mood oscillation and emotional cascading. |
| 7 | **HMAC** | `CheckpointManager` | SHA-256 HMAC on checkpoint payloads. Key from `TELOS_CHECKPOINT_SECRET` env var (defaults to dev key). Rejects tampered checkpoints. |
| 8 | **Provenance** | `KnowledgeGraph` | Every record stores `source/cycle/caller` provenance. Internal domains (`mission_policy`, `stream_calibrator`, etc.) are read-only from KG perspective. Write domains whitelisted. |
| 9 | **PolicyChangeLog** | `MissionPolicyManager` | Full audit trail of all policy changes. MAX_CHANGES=1000. Every adjustment recorded with old/new value, reason, caller, cycle. Enables rollback from audit log. |
| 10 | **Constitutional Firewall** | `DecisionFirewall` | 6 constitutional checks: (1) Council validation, (2) DI threshold (domain-specific), (3) Mission violation, (4) Intent validity, (5) Loop detection (same action ≥3 cycles), (6) Identity integrity (mood-based elevated threshold for uncertain/fatigued). |

---

## 4. Data Flow Integrity Patterns (DFI-01 to DFI-05)

These patterns describe the invariant data flow paths through the TELOS architecture. Violating any of these patterns constitutes an architectural leak.

### DFI-01: Pipeline ←→ World (Bidirectional, Phase-Locked)
```
World facts flow INTO the Pipeline at PERCEIVE.
Action intents flow OUT of the Pipeline at ACT.
No domain data persists within the Pipeline between cycles.
```
**Violation:** Storing domain state in `PhaseContext` across cycles.

### DFI-02: InfraManager ⊥ Pipeline (Observer Pattern)
```
InfraManager observes PipelineResult after each execute().
InfraManager adjusts calibrations → Pipeline reads them next cycle.
InfraManager NEVER modifies Pipeline state directly.
```
**Violation:** Calling `pipeline.register_stream()` or `pipeline.set_config()` from `InfraManager.observe()`.

### DFI-03: ExperienceManager ∉ Pipeline (External Learner)
```
ExperienceManager lives OUTSIDE the Pipeline.
It receives PipelineResult, indexes Skills, and writes to SkillLibrary.
The Pipeline only READS from SkillLibrary via MemoryStream.
```
**Violation:** Calling `ExperienceManager.observe()` from within a Pipeline phase.

### DFI-04: Council ⊥ DecisionFirewall (Serial Gates)
```
Council validates intent → returns verdict.
DecisionFirewall audits the full decision path → returns verdict.
Firewall blocks if Council blocked (second-opinion enforcement).
Both gates must pass before ACT phase executes.
```
**Violation:** Bypassing Council and going directly to ActPhase.

### DFI-05: KnowledgeGraph ⊣ Internal Domains (Read-Only Boundary)
```
Internal domains (mission_policy, stream_calibrator, failure_ledger,
system_self, identity, governance, firewall) cannot be written to KG.
External domains (gridworld, devdomain, navigation, etc.) can be written.
KG recommendations flow INTO Pipeline but NOT INTO internal configuration.
```
**Violation:** Storing internal calibration parameters as KnowledgeGraph nodes.

---

## 5. The Three-Layer Identity Model

TELOS's cognitive identity operates at three distinct layers, each with different persistence, mutability, and scope characteristics.

### Layer 1: CLI Infrastructure (Persistent, Slow-Burning)
- **Location:** `SystemSelf` (`core/identity/system_self.py`), `IdentityState`
- **Components:** mood, confidence_trend, exploration_appetite, resilience, identity_markers
- **Persistence:** Saved to JSON checkpoint; restored on restart with genesis mood anchoring
- **Change rate:** Mood changes max once per 20 cycles
- **Function:** Shapes risk tolerance, exploration budget, and decision firewalling via `get_risk_adjustment()` and `get_exploration_adjustment()`

**Mood ladder:**
```
curious (genesis) → confident → stable → cautious → uncertain → fatigued
```
Mood can never drift more than 2 steps from genesis (`MOOD_MAX_STEPS_FROM_GENESIS = 2`). If a checkpoint attempts to restore a mood too far from genesis, the system reverts to `curious`.

### Layer 2: Model Identity (Per-Session, Evidence-Grounded)
- **Location:** `StreamCalibrator` (`core/infra_manager/stream_calibrator.py`), `ExperienceMap`
- **Components:** Per-stream influence weights, experience maps, confidence distributions
- **Persistence:** Rebuilt from observations each session
- **Function:** Determines which streams have authority in which contexts

**Experience accumulation:**
```python
uncertainty = confidence_std / sqrt(n_observations)
```
Each context a stream encounters builds a calibrated confidence distribution. Streams with many observations in a context speak with higher certainty.

### Layer 3: Emergent Cognition (Per-Cycle, Transient)
- **Location:** `WorldLedger` (`core/ledger/world_ledger.py`), `SemanticDepth`
- **Components:** Entity records with 4-layer semantic depth ladder
- **Persistence:** Ephemeral per cycle; entity records persist but semantic depths are recomputed
- **Function:** The "I" of the moment — what the system perceives itself to be in this cycle

**Semantic Depth Ladder:**
```
Layer 1 — Observable:    Current features from PerceptionStream
Layer 2 — Historical:    "newly_discovered" → "observed_N_times" → "well_known_M_observations"
Layer 3 — Mission:       relevance to current mission vector (0.0 - 1.0)
Layer 4 — Identity:      synthesized meaning (e.g., "active_region_persistent_entity_high_mission_priority")
```

---

## 6. Store Boundary Normalization Principle

**"Every data store in TELOS must have a clearly defined boundary, ownership, and access pattern. No two stores may overlap in responsibility."**

| Store | Owner | Data | Access Pattern |
|-------|-------|------|----------------|
| `WorldLedger` | Pipeline | Entity records, user profiles | Enrich → Read via PERCEIVE phase |
| `SkillLibrary` | ExperienceManager | Indexed skills from past decisions | Write via ExperienceManager, Read via MemoryStream |
| `FailureLedger` | InfraManager | Failure records with root causes | Write via failure detection, Read via MemoryAdvisor |
| `KnowledgeGraph` | KnowledgeManager | Proven solutions and failures by domain | Write via KnowledgeManager, Read via consult_knowledge |
| `SystemSelf` | InfraManager | Cognitive identity state | Write via observe(), Read via get_risk_adjustment() |
| `CheckpointManager` | InfraManager | Full pipeline snapshots | Write after each execute(), Read on restart |
| `PatternLibrary` | ReflectPhase | Cross-domain pattern signatures | Write via Reflect, Read via pattern matching |
| `PlanningHorizon` | Pipeline | Multi-cycle plan sequences | Write via select, Read via PERCEIVE |

**Principle:** No component outside the designated owner may write to a store. Reading is permitted through defined API methods only. Direct store mutation (e.g., `ledger._records.clear()`) is prohibited outside tests.

---

## 7. DI/MD Governance Metrics

### Decision Integrity (DI)
**Formula:**
```
DI = 1 - sum(IgnoredEvidence × BeliefConfidence) / TotalAvailableEvidence
```

- DI = 1.0 → fully evidence-led. No evidence was ignored.
- DI < 1.0 → some evidence was disregarded in favor of belief.
- When any validator BLOCKs, DI is capped at `DISSENT_FLOOR = 0.3` (prevents evidence-weight manipulation).

**Evidence weighting:**
```python
for each validator signal:
    effective_weight = signal.evidence_weight
    if evidence_weights override exists:
        effective_weight *= evidence_weights[validator_name]
    if signal is a BLOCK (not passed):
        ignored += effective_weight × abs(signal.confidence)
DI = 1.0 - ignored / total_evidence
```

### Mission Drift (MD)
**Formula:**
```
MD = ||PredictedState - ObservedState||
```

- MD = 0.0 → perfect prediction. Simulation matches reality.
- MD > drift_threshold (default 5.0) → instantaneous block.
- Cumulative MD > cumulative_threshold (default 10.0) → cumulative block.
- Drift history maintained as sliding window of max 100 observations.

### DissentFloor
```
When any validator returns BLOCK:
    DI = min(DI, 0.3)   # DI cannot exceed 0.3

This ensures that even if evidence-weight manipulation makes 
the numerical DI calculation appear high, the presence of 
legitimate dissent caps the score.
```

### Governance Block Conditions
The `DecisionFirewall` performs 6 constitutional checks:
1. **Council validation** — if Council rejected, Firewall upholds the block
2. **Decision integrity** — DI must meet domain-specific threshold (gridworld: 0.3, devdomain: 0.6, default: 0.4)
3. **Mission violation** — action must not violate mission parameters
4. **Intent validity** — intent must not be None
5. **Loop detection** — same action repeated ≥3 consecutive cycles
6. **Identity integrity** — if mood is `uncertain` or `fatigued`, DI threshold elevated by 1.5× (min 0.5)

### Typical Values
| State | DI | MD | Interpretation |
|-------|----|----|----------------|
| Healthy | 0.85-1.0 | 0.0-1.0 | Strong evidence-led, well-calibrated model |
| Warning | 0.5-0.85 | 1.0-3.0 | Some evidence ignored, model drifting |
| Degraded | 0.3-0.5 | 3.0-5.0 | Significant evidence rejection, model divergence |
| Critical | <0.3 | >5.0 | Governance intervention likely, recovery mode probable |

---

## 8. The TELOS Commitment Principle (Axiom 5.1)

> *"An intelligent agent should commit only the fraction of its finite resources that maximizes long-term trajectory quality while preserving identity, maintaining recovery capacity, and keeping future options open."*

### The Commitment Equation

$$C^* = \arg\max_{C} \Big[ \mathbb{E}(R) - M(C) - Rec(C) - I(C) + F(C) \Big]$$

Where:
- $\mathbb{E}(R)$: **Expected Future Reward** from the decision
- $M(C)$: **Maintenance Cost** — ongoing overhead to sustain commitment
- $Rec(C)$: **Recovery Cost** — resources needed if the path fails
- $I(C)$: **Identity Cost** — structural damage or constraint narrowing
- $F(C)$: **Future Opportunity Preservation** — option value remaining after commitment

### The Kelly-TELOS Relation

The **Kelly Criterion** ($f^* = \frac{bp-q}{b}$) is a limiting case of TELOS Commitment Theory:

$$\text{Kelly Criterion} \subset \text{TELOS Commitment Theory}$$

When the only resource is capital, identity cost is zero, maintenance and recovery costs are zero, and future option value is zero, the TELOS equation collapses to risk-neutral expected value maximization:

$$C^*_{\text{Kelly}} = \arg\max[ \mathbb{E}(R) ]$$

### Dynamic Commitment

| State | C* | Behavior |
|-------|----|----------|
| High entropy, collapsing identity | Low (< 0.3) | Explore, don't commit |
| High recovery ratio, firefighting | Low (< 0.3) | Recover, don't commit |
| High counterfactual diversity | Boosted (+0.15 max) | Explore more aggressively |
| Stable identity, low costs | High (> 0.8) | Full commitment justified |

The `CommitmentOptimizer` (`core/decision/commitment_optimizer.py`) implements this equation, and the `SelectPhase` applies the commitment score to modulate intent weights before action selection.

**Implementation evidence:**
- `core/decision/commitment_optimizer.py` — `CommitmentScore.commitment` property computes `C* = E(R) - M - Rec - I + F`
- `core/phases/select.py:14-50` — pipeline reads identity entropy, cost tracker, and diversity; feeds into CommitmentOptimizer.evaluate()
- `core/phases/perceive.py:11-63` — low commitment feeds back into attention allocation, boosting opportunity exploration
- `AXIOMS.md:42-43` — documented as Axiom 5.1

---

*"The measure of intelligence is not how confidently a system acts, but how well it exposes, evaluates, and integrates inconvenient truths before acting."*
*— The Principle of Epistemic Integrity*
