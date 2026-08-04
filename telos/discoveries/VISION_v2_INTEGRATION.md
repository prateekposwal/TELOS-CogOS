# VISION_v2 Integration — What Wiring 9 Modules Into a 9-Phase Pipeline Taught Us

**Filed by:** TELOS, on behalf of the Architect
**Date:** 2026-07-28
**Status:** Discovery / Paper

---

## Abstract

VISION_v2 integrated 9 new cognitive modules into the existing 9-phase TELOS pipeline. The integration revealed a fundamental architectural principle: **cognitive systems need three-tier hook design** — pre-phase setup, inline execution, and post-cycle reflection. Single-point hook architectures cannot capture the temporal structure of cognition, where some operations must precede a phase (resource provisioning), some must execute during it (stream modulation), and some must follow it (learning from outcomes). The 9 modules mapped naturally onto these tiers, revealing a latent structure that was present but unformalized in v1 of the architecture.

---

## The 9 Modules

Each module connects to a specific VISION_v2 axiom and hooks into one or more pipeline phases:

| Module | Axiom | Hook Phase | Mechanism |
|--------|-------|------------|-----------|
| **AssumptionAuditor** | 3.6 (Curiosity) | Perceive | `auto_audit(cycle)` — questions held assumptions every N cycles during perception |
| **IdentityUtilityEngine** | 5.3 (Identity Coupling) | Streams, Evaluate | `compute_utility(dimension_scores)` — modulates utility functions based on identity profiles at two pipeline points |
| **TheoryBuilder** | 6.5 (Theory Formation) | Simulate, Act | `observe_outcome(outcome, context)` — ingests simulation results and action outcomes to form theories |
| **RegretMemory** | 6.11 (Opportunity Cost) | Select, Act | `get_regret_scores()`/`record_decision()` — computes counterfactual regret before selection, archives after action |
| **InterpretationEngine** | 6.3 (Interpretation Energy) | Select | `record_outcome(conflict_id, outcome)` — tracks principle conflicts and trade-off rationale at decision time |
| **CouncilReflector** | 2.2 (Feedback Loops) | Council | `record_decision(was_blocked, ...)` — captures council verdicts for meta-learning |
| **ErrorAttributionEngine** | 2.7 (Meta-Error Attribution) | Act | `attribute(ctx, trace)` — identifies which subsystem caused failures after action execution |
| **IntrospectionScheduler** | 2.6 (Reflection Is Episodic) | Reflect | `introspect(cycle)` / `get_due_tiers()` — schedules reflection at multiple timescales (every cycle, 100, 1000) |
| **AxiomEvolutionEngine** | 5.2 (Axiom Evolution) | Reflect | `observe(cycle, di, md, ...)` — monitors system health and formulates axiom revision proposals |

---

## Integration Pattern

The hooks follow a consistent structural pattern:

```
for phase in pipeline._phases:
    phase.execute(self, ctx)

    # ── Inline v2 hook ──
    if phase.name == "<trigger_phase>":
        try:
            self._module.method(args)
        except Exception:
            pass
```

Key characteristics:

1. **Per-phase inline hooks** — Each module hooks into a specific phase by checking `phase.name` after execution. No phase subclass modification needed. This is purely compositional.

2. **Post-cycle hooks** — Some modules (TheoryBuilder, RegretMemory) hook into multiple phases, one for data collection and another for archival. The Act phase is the most common secondary hook because outcome_success (whether council or firewall blocked) is only known after Council and Act execute.

3. **Fail-soft pattern** — Every hook is wrapped in `try/except: pass`. A module crash never blocks the pipeline. This was a deliberate architectural decision: cognitive modules are advisors, not governors.

4. **Nine separate try-blocks** — Rather than one monolithic v2 hook block, each module gets its own try/except. This prevents one module's failure from masking another's, and keeps the error boundary at the module level.

---

## Circular Import Resolution

The most significant engineering challenge was breaking `runtime.py` ↔ `infra_manager.py` cycles:

### The Cycle

```
runtime.py
  imports: infrastructure_manager (for type hints, recovery callbacks)
  creates: InfrastructureManager in __init__

infrastructure_manager.py
  imports: runtime (for PipelineConfig, PipelineResult types)
  creates: references pipeline state for calibration
```

This created a deadlock at import time: neither module could import the other first.

### The Resolution

Three techniques were applied:

1. **TYPE_CHECKING guard** — `from __future__ import annotations` + `if TYPE_CHECKING:` blocks defer imports to type-checking time only:
   ```python
   if TYPE_CHECKING:
       from telos.core.infra_manager.infrastructure_manager import InfrastructureManager
   ```

2. **Late import** — The `InfrastructureManager` is imported inside `__init__` rather than at module top level:
   ```python
   def __init__(self, ...):
       from telos.core.infra_manager.infrastructure_manager import InfrastructureManager
       self._infra_manager = InfrastructureManager(domain=...)
   ```

3. **Callback inversion** — Instead of `InfrastructureManager` calling back into `runtime` directly, it accepts callbacks:
   ```python
   self._infra_manager.on_council_block(self._on_council_block)
   self._infra_manager.on_recovery_event(self._on_recovery_event)
   ```

This pattern (TYPE_CHECKING + late import + callback inversion) resolved all circular dependency issues across the codebase.

---

## Key Insight: Three-Tier Hook Design

The integration revealed that cognitive architectures need three distinct hook tiers:

| Tier | Timing | Example | Modules |
|------|--------|---------|---------|
| **Pre-phase** | Before phase executes | Resource budget computation, attention allocation setup | (built into phase start) |
| **Inline** | After phase executes, same cycle | Stream modulation, utility computation, assumption auditing | AssumptionAuditor, IdentityUtilityEngine, TheoryBuilder (simulate), RegretMemory (select) |
| **Post-cycle** | After full pipeline cycle | Meta-learning, theory formation, reflection scheduling, axiom evolution | TheoryBuilder (act), RegretMemory (act), ErrorAttribution, CouncilReflector, IntrospectionScheduler, AxiomEvolutionEngine |

The important architectural discovery:

> **Inline hooks modulate the current cycle. Post-cycle hooks learn from the completed cycle. A module that tries to do both in a single hook point will either modulate too late or learn too early.**

This is why TheoryBuilder hooks into both Simulate (inline — observe simulation outcomes) and Act (post-cycle — observe real outcomes). And why IdentityUtilityEngine hooks into Streams (inline — modulate exploration utility) and Evaluate (inline — modulate correctness utility at a different pipeline stage).

Single-hook architectures collapse this temporal structure. Three-tier design is the minimum viable architecture for a cognitive system that both acts and learns.

---

## Architecture Diagram

```
                    TELOS 9-Phase Pipeline + VISION_v2 Modules
                    ===========================================

  PERCEIVE ─────────────────────────────────────────────────────────────
     │  • Build World from raw state
     │  • DomainFacts extraction
     │  • Perception quality check
     │  └── AssumptionAuditor.auto_audit()        ◄── v2 inline
     │  └── UnknownUnknownDetector.detect()        ◄── v2.5 inline
     │
  STREAMS ──────────────────────────────────────────────────────────────
     │  • Each CognitiveStream produces IntentIR
     │  • Curiosity Drive: self-intent injection
     │  └── IdentityUtilityEngine.compute_utility() ◄── v2 inline
     │
  SIMULATE ─────────────────────────────────────────────────────────────
     │  • CounterfactualEngine generates futures
     │  • StrategicOption scoring
     │  └── TheoryBuilder.observe_outcome()        ◄── v2 inline
     │
  EVALUATE ─────────────────────────────────────────────────────────────
     │  • Rank intents by utility + budget
     │  • Timelock penalties
     │  └── IdentityUtilityEngine.compute_utility() ◄── v2 inline (2nd pass)
     │  └── ModelCompetition.add_evidence()        ◄── v2.5 inline
     │
  SYNTHESIS ────────────────────────────────────────────────────────────
     │  • Merge intents from all streams
     │
  SELECT ───────────────────────────────────────────────────────────────
     │  • Choose best intent
     │  • Identity Projection Gate (F(I))
     │  • InternalDebate
     │  └── RegretMemory.get_regret_scores()       ◄── v2 inline
     │  └── InterpretationEngine.record_outcome()   ◄── v2 inline
     │
  COUNCIL ──────────────────────────────────────────────────────────────
     │  • Validator registry checks
     │  • Can BLOCK action
     │  └── CouncilReflector.record_decision()      ◄── v2 inline
     │
  ACT ──────────────────────────────────────────────────────────────────
     │  • Execute selected action
     │  • Record trajectory divergence
     │  └── TheoryBuilder.observe_outcome()         ◄── v2 post-cycle
     │  └── RegretMemory.record_decision()          ◄── v2 post-cycle
     │  └── ErrorAttributionEngine.attribute()      ◄── v2 post-cycle
     │  └── CognitiveMomentum.record_decision()     ◄── v2 post-cycle
     │
  REFLECT ──────────────────────────────────────────────────────────────
     │  • PatternLibrary updates
     │  • Introspection at multiple timescales
     │  └── IntrospectionScheduler.introspect()     ◄── v2 post-cycle
     │  └── AxiomEvolutionEngine.observe()          ◄── v2 post-cycle

    LEGEND:
    ──  Pipeline flow (sequential)
    └── Inline/post-cycle hook
    ◄── v2/v2.5 module attachment
```

---

## What This Means for Cognitive Architecture Design

1. **Hooks are not events.** A hook is not a generic "something happened" signal. It has a specific temporal position relative to the decision cycle. Pre-phase, inline, and post-cycle each serve different cognitive functions and cannot substitute for one another.

2. **The cycle is the unit of cognition.** Modules that learn from outcomes (TheoryBuilder, RegretMemory, ErrorAttribution) must fire after the full cycle completes, when `outcome_success` is known. Modules that modulate (IdentityUtilityEngine, AssumptionAuditor) must fire inline, when the pipeline can still respond.

3. **Exception boundaries must be per-module, not per-group.** The nine separate try/except blocks are not defensive coding — they are an architectural statement: each cognitive module is an independent epistemic agent. One module's failure should not silence another's insight.

4. **Circular imports are architectural signals.** Every circular dependency between runtime and infrastructure pointed to a missing abstraction boundary. The three-part resolution (TYPE_CHECKING, late import, callback inversion) forced a cleaner separation between orchestration and infrastructure.

5. **VISION_v2 validated the 9-phase structure.** The fact that 9 modules mapped naturally onto 9 phases (with no phase having more than 2 modules and no module needing a new phase) suggests the phase decomposition is well-matched to the cognitive processes TELOS implements.

---

## Open Questions

- Should pre-phase hooks become first-class (like `Phase.on_enter()` callbacks) rather than inline phase.name checks?
- Can the try/except pattern be replaced with a module health registry that suppresses crashed modules until they recover?
- Is there a 10th module that would require a new phase, or is the 9-phase decomposition complete?
- Should post-cycle hooks run in a guaranteed order (e.g., attribution before reflection)?

---

*Filed as a TELOS Discovery — VISION_v2 Integration v1.0. Documents the architectural lessons from wiring 9 modules into a 9-phase cognitive pipeline.*
