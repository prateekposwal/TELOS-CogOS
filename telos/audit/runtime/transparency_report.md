# TELOS Transparency Report
**Generated:** 2026-07-27 02:35:54
**Total Decision Cycles:** 5

## Principle of Latent Cognition

> "An intelligent system is defined not by the number of visible capabilities
> it possesses, but by the invisible coordination of latent cognitive processes
> working toward a unified mission."

## Principle of Epistemic Integrity

> "An intelligent system is not defined by how confidently it pursues a mission,
> but by its ability to continuously expose, evaluate, and integrate
> inconvenient truths before acting."

This report provides empirical evidence of both principles by exposing the
internal stream activations, budget allocations, Council validations, and
decision traces that produced each visible action.

---

## System Summary

| Metric | Value |
|--------|-------|
| Cycles | 5 |
| Stream Activations | 12/16 |
| Activation Rate | 75.0% |
| Total Budget Consumed | -124.0ms |
| Average Health | 1.248 |
| Average Decision Integrity (DI) | 1.000 |
| Average Mission Drift (MD) | 0.201 |
| Council-Blocked Cycles | 0 |

### Decision Integrity (DI)

DI = 1 - sum(IgnoredEvidence × BeliefConfidence) / TotalAvailableEvidence

Average DI of 1.000 means the system is strongly evidence-led across all cycles.

### Mission Drift (MD)

MD = ||PredictedState - ObservedState||

Average MD of 0.201 means the system's world model is well-calibrated.

---

## Decision Cycle Details

### Cycle 1
- **Duration:** 2.95ms
- **Budget:** 16.0/100.0ms
- **Health:** 0.840
- **Representation:** spatial
- **Worlds Simulated:** 1
- **Council: ✅ APPROVED**
- **DI:** 1.000
- **MD:** 0.237

**Stream Activations (Latent Processes):**

| Stream | Priority | Activated | Intent | Cost |
|--------|----------|-----------|--------|------|
| ReflexStream | 1.0 | yes | reflex | 0.01ms |
| PerceptionStream | 0.9 | yes | perceive | 0.04ms |
| MemoryStream | 0.7 | yes | memory_miss | 0.01ms |
| PlanningStream | 0.5 | yes | plan_trajectory | 0.92ms |

**Governance (Cognitive Confidentiality):**

| Check | Passed | Reason |
|-------|--------|--------|
| all_governance_checks | ✅ | All governance checks passed |

**Semantic Depth (Cognitive Identity):**

| Entity | Observable | Historical | Mission | Identity |
|--------|------------|------------|---------|----------|
| `ent_5570` | norm=2.2 | newly_discovered | relevance_0.31 | `active_region` |

**Strategic Options (Alternative Futures):**

  - Rank #1: score=0.3155, horizon=5

**Decision Trace:**
- Intent: `perceive`
- Confidence: 0.850


---

### Cycle 2
- **Duration:** 3.00ms
- **Budget:** -35.0/100.0ms
- **Health:** 1.350
- **Representation:** spatial
- **Worlds Simulated:** 1
- **Council: ✅ APPROVED**
- **DI:** 1.000
- **MD:** 0.219

**Stream Activations (Latent Processes):**

| Stream | Priority | Activated | Intent | Cost |
|--------|----------|-----------|--------|------|
| PerceptionStream | 0.9 | SKIPPED | - | 0.00ms |
| ReflexStream | 1.0 | yes | reflex | 0.01ms |
| MemoryStream | 0.7 | yes | memory_recall | 0.01ms |

**Governance (Cognitive Confidentiality):**

| Check | Passed | Reason |
|-------|--------|--------|
| all_governance_checks | ✅ | All governance checks passed |

**Strategic Options (Alternative Futures):**

  - Rank #1: score=0.3100, horizon=5

**Decision Trace:**
- Intent: `perceive`
- Confidence: 0.850


---

### Cycle 3
- **Duration:** 1.63ms
- **Budget:** -35.0/100.0ms
- **Health:** 1.350
- **Representation:** spatial
- **Worlds Simulated:** 1
- **Council: ✅ APPROVED**
- **DI:** 1.000
- **MD:** 0.144

**Stream Activations (Latent Processes):**

| Stream | Priority | Activated | Intent | Cost |
|--------|----------|-----------|--------|------|
| PerceptionStream | 0.9 | SKIPPED | - | 0.00ms |
| ReflexStream | 1.0 | yes | reflex | 0.01ms |
| MemoryStream | 0.7 | yes | memory_recall | 0.01ms |

**Governance (Cognitive Confidentiality):**

| Check | Passed | Reason |
|-------|--------|--------|
| all_governance_checks | ✅ | All governance checks passed |

**Strategic Options (Alternative Futures):**

  - Rank #1: score=0.3029, horizon=5

**Decision Trace:**
- Intent: `perceive`
- Confidence: 0.850


---

### Cycle 4
- **Duration:** 1.90ms
- **Budget:** -35.0/100.0ms
- **Health:** 1.350
- **Representation:** spatial
- **Worlds Simulated:** 1
- **Council: ✅ APPROVED**
- **DI:** 1.000
- **MD:** 0.147

  🔒 **Firewall Blocked:** `action_loop`

**Stream Activations (Latent Processes):**

| Stream | Priority | Activated | Intent | Cost |
|--------|----------|-----------|--------|------|
| PerceptionStream | 0.9 | SKIPPED | - | 0.00ms |
| ReflexStream | 1.0 | yes | reflex | 0.01ms |
| MemoryStream | 0.7 | yes | memory_recall | 0.01ms |

**Governance (Cognitive Confidentiality):**

| Check | Passed | Reason |
|-------|--------|--------|
| loop_detection | ❌ | Same action 'perceive' repeated 4+ consecutive cycles |

**Strategic Options (Alternative Futures):**

  - Rank #1: score=0.2970, horizon=5

**Decision Trace:**
- Intent: `perceive`
- Confidence: 0.850


---

### Cycle 5
- **Duration:** 1.91ms
- **Budget:** -35.0/100.0ms
- **Health:** 1.350
- **Representation:** spatial
- **Worlds Simulated:** 1
- **Council: ✅ APPROVED**
- **DI:** 1.000
- **MD:** 0.259

  🔒 **Firewall Blocked:** `action_loop`

**Stream Activations (Latent Processes):**

| Stream | Priority | Activated | Intent | Cost |
|--------|----------|-----------|--------|------|
| PerceptionStream | 0.9 | SKIPPED | - | 0.00ms |
| ReflexStream | 1.0 | yes | reflex | 0.00ms |
| MemoryStream | 0.7 | yes | memory_recall | 0.01ms |

**Governance (Cognitive Confidentiality):**

| Check | Passed | Reason |
|-------|--------|--------|
| loop_detection | ❌ | Same action 'perceive' repeated 4+ consecutive cycles |

**Strategic Options (Alternative Futures):**

  - Rank #1: score=0.2998, horizon=5

**Decision Trace:**
- Intent: `perceive`
- Confidence: 0.850


---
