# TELOS Transparency Report
**Generated:** 2026-08-11 02:39:00
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
| Total Budget Consumed | -123.3ms |
| Average Health | 1.247 |
| Average Decision Integrity (DI) | 1.000 |
| Average Mission Drift (MD) | 0.164 |
| Council-Blocked Cycles | 0 |

### Decision Integrity (DI)

DI = 1 - sum(IgnoredEvidence × BeliefConfidence) / TotalAvailableEvidence

Average DI of 1.000 means the system is strongly evidence-led across all cycles.

### Mission Drift (MD)

MD = ||PredictedState - ObservedState||

Average MD of 0.164 means the system's world model is well-calibrated.

---

## Decision Cycle Details

### Cycle 1
- **Duration:** 4.86ms
- **Budget:** 16.6/100.0ms
- **Health:** 0.834
- **Representation:** spatial
- **Worlds Simulated:** 1
- **Council: ✅ APPROVED**
- **DI:** 1.000
- **MD:** 0.253

**Stream Activations (Latent Processes):**

| Stream | Priority | Activated | Intent | Cost |
|--------|----------|-----------|--------|------|
| ReflexStream | 1.0 | yes | reflex | 0.02ms |
| PerceptionStream | 0.9 | yes | perceive | 0.07ms |
| MemoryStream | 0.7 | yes | memory_miss | 0.01ms |
| PlanningStream | 0.5 | yes | plan_trajectory | 1.48ms |

**Governance (Cognitive Confidentiality):**

| Check | Passed | Reason |
|-------|--------|--------|
| all_governance_checks | ✅ | All governance checks passed |

**Semantic Depth (Cognitive Identity):**

| Entity | Observable | Historical | Mission | Identity |
|--------|------------|------------|---------|----------|
| `ent_5570` | norm=2.2 | newly_discovered | relevance_0.31 | `active_region` |

**Strategic Options (Alternative Futures):**

  - Rank #1: score=0.3173, horizon=5

**Decision Trace:**
- Intent: `perceive`
- Confidence: 0.850


---

### Cycle 2
- **Duration:** 3.44ms
- **Budget:** -35.0/100.0ms
- **Health:** 1.350
- **Representation:** spatial
- **Worlds Simulated:** 1
- **Council: ✅ APPROVED**
- **DI:** 1.000
- **MD:** 0.173

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

  - Rank #1: score=0.3091, horizon=5

**Decision Trace:**
- Intent: `perceive`
- Confidence: 0.850


---

### Cycle 3
- **Duration:** 2.05ms
- **Budget:** -35.0/100.0ms
- **Health:** 1.350
- **Representation:** spatial
- **Worlds Simulated:** 1
- **Council: ✅ APPROVED**
- **DI:** 1.000
- **MD:** 0.152

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

  - Rank #1: score=0.3134, horizon=5

**Decision Trace:**
- Intent: `perceive`
- Confidence: 0.850


---

### Cycle 4
- **Duration:** 2.57ms
- **Budget:** -35.0/100.0ms
- **Health:** 1.350
- **Representation:** spatial
- **Worlds Simulated:** 1
- **Council: ✅ APPROVED**
- **DI:** 1.000
- **MD:** 0.127

  🔒 **Firewall Blocked:** `action_loop`

**Stream Activations (Latent Processes):**

| Stream | Priority | Activated | Intent | Cost |
|--------|----------|-----------|--------|------|
| PerceptionStream | 0.9 | SKIPPED | - | 0.00ms |
| ReflexStream | 1.0 | yes | reflex | 0.02ms |
| MemoryStream | 0.7 | yes | memory_recall | 0.03ms |

**Governance (Cognitive Confidentiality):**

| Check | Passed | Reason |
|-------|--------|--------|
| loop_detection | ❌ | Same action 'perceive' repeated 4+ consecutive cycles |

**Strategic Options (Alternative Futures):**

  - Rank #1: score=0.2991, horizon=5

**Decision Trace:**
- Intent: `perceive`
- Confidence: 0.850


---

### Cycle 5
- **Duration:** 2.43ms
- **Budget:** -35.0/100.0ms
- **Health:** 1.350
- **Representation:** spatial
- **Worlds Simulated:** 1
- **Council: ✅ APPROVED**
- **DI:** 1.000
- **MD:** 0.117

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

  - Rank #1: score=0.3064, horizon=5

**Decision Trace:**
- Intent: `perceive`
- Confidence: 0.850


---
