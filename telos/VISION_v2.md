# TELOS v2 — Architectural Vision

*Based on Prateek's architectural feedback — July 26, 2026*

---

## The Insight

Prateek gave 9 architectural insights that form the blueprint for TELOS v2.
These are NOT feature requests — they are **architectural invariants** for the
next generation of the system. Every one is implementable. Every one fills
a gap in the current 20 axioms.

> *"An intelligent system is defined not by the number of visible capabilities it possesses,
> but by the invisible coordination of latent cognitive processes working toward a unified mission."*
> — TELOS Genesis

---

## The 9 Insights

### 1. Council Must Update Itself (Meta-Learning)
**Implemented:** `telos/core/council/reflector.py`

The Council currently blocks or passes but never asks "was I right?" afterwards.
CouncilReflector adds a hindsight loop: after action, compare prediction to outcome
and update validator confidence weights.

**Next steps:**
- Wire CouncilReflector into `CouncilPhase` to automatically reflect after each cycle
- Use `get_validator_confidence_adjustments()` to modulate evidence weights in next cycle
- Add automatic re-weighting in `Council.evaluate()`

### 2. Meta-Error Attribution
**Implemented:** `telos/core/meta/error_attribution.py`

The system says "I made a mistake" but never identifies *which subsystem* caused it.
ErrorAttributionEngine traces each error to perception, simulation, council, governance,
or execution — and tracks error rates per subsystem.

**Next steps:**
- Wire into `ActPhase` and `ReflectPhase` for automatic attribution
- Add automatic repair: if COUNCIL is the most erratic, adjust validator thresholds
- Surface subsystem health in dashboard telemetry

### 3. Curiosity Should Question Assumptions
**Implemented:** `telos/core/curiosity/assumption_auditor.py`

The current CuriosityDrive explores physical space (counterfactual worlds) but never
questions its own assumptions. The AssumptionAuditor tracks active assumptions and
audits them when curiosity is high.

**Next steps:**
- Wire into `CuriosityDrive.update()` to auto-trigger audits
- Connect to TheoryBuilder: failed assumptions can seed new hypotheses
- Add periodic assumption review in IntrospectionScheduler's REFLECT tier

### 4. Identity Changes Utility Functions
**Implemented:** `telos/core/identity/utility_profiles.py`

The current SystemSelf changes mood (thresholds) but never changes the fundamental
utility function. IdentityUtilityEngine defines profiles with different weightings:
REDACTED = maximize collaboration, TELOS = maximize correctness, Explorer = maximize learning.

**Next steps:**
- Replace SelectPhase's hardcoded scoring with `IdentityUtilityEngine.compute_utility()`
- Wire identity_markers from SystemSelf to auto-select the right profile
- Add profile transitions based on mood + context

### 5. Multi-Timescale Introspection
**Implemented:** `telos/core/introspection/scheduler.py`

Three tiers of introspection:
- **Tier 1 (every cycle):** "Did that action work?" — predicted vs actual state
- **Tier 2 (every ~100 cycles):** "What patterns are emerging?" — recurring blocks, skill diversity
- **Tier 3 (every ~1000 cycles):** "Should I change strategy?" — identity trajectory, axiom scores

**Next steps:**
- Wire into pipeline's main `execute()` loop with `get_due_tiers()` check
- Connect Tier 2 to TheoryBuilder for pattern discovery
- Connect Tier 3 to AxiomEvolutionEngine for axiom proposals

### 6. Regret Memory
**Implemented:** `telos/core/memory/regret_memory.py`

Counterfactual history that answers "would alternative B have been better?"
Regret = utility(chosen) - utility(best_alternative). Tracked per decision type,
per stream, with blind spot detection.

**Next steps:**
- Wire into `SelectPhase` to capture counterfactual options before selection
- Wire into `ActPhase` to retroactively evaluate after outcome
- Connect to TheoryBuilder: high-regret decisions seed hypotheses
- Surface blind spots in dashboard

### 7. Theory Builder
**Implemented:** `telos/core/reasoning/theory_builder.py`

Abstraction pipeline: Experience → Cluster → Hypothesis → Test → Theory.
The system currently stores experiences but never abstracts from them.
The TheoryBuilder builds falsifiable theories from experience patterns.

**Next steps:**
- Wire into `ReflectPhase` for periodic theory building
- Wire into `ExperienceManager.observe()` to auto-add experiences
- Use theories to guide simulation: theory-consistent worlds get higher priors
- Add cross-domain theory transfer

### 8. Axiom Evolution (Proposal)
**Implemented (proposal):** `telos/core/axioms/evolution.py`

The system monitors its own behavior and proposes new axioms when it detects gaps
in the existing 20. Axiom proposals require human approval — the system never
self-edits axioms.

**Next steps:**
- Wire into `IntrospectionScheduler`'s STRATEGIC tier
- Implement HumanGateway approval workflow
- Add axiom satisfaction tracking per cycle
- After approval, auto-integrate new axiom into pipeline

### 9. Interpretation Engine (Proposal)
**Implemented (proposal):** `telos/core/reasoning/interpretation_engine.py`

When principles conflict (e.g., correctness vs speed, exploration vs safety),
the engine generates explanations, estimates trade-offs, and archives rationale.
Resolution strategies can be learned from past conflicts.

**Next steps:**
- Wire into `SynthesisPhase` to detect principle conflicts
- Wire into `SelectPhase` to inform trade-off decisions
- Build conflict resolution strategy from past outcomes
- Add dashboard visualization of active conflicts

---

## Integration Map

```
Pipeline Phase          →  New Component
──────────────────────────────────────────────────
PERCEIVE                →  AssumptionAuditor (register world assumptions)
STREAMS                 →  IdentityUtilityEngine (select profile)
SIMULATE                →  TheoryBuilder (seed simulations from theories)
EVALUATE                →  IdentityUtilityEngine (compute utility by profile)
SELECT                  →  RegretMemory (capture counterfactuals)
                         →  InterpretationEngine (resolve principle conflicts)
COUNCIL                 →  CouncilReflector (validate post-hoc)
ACT                     →  ErrorAttributionEngine (attribute outcome errors)
REFLECT                 →  IntrospectionScheduler (tiered introspection)
                         →  TheoryBuilder (cluster → hypothesize → promote)
                         →  AxiomEvolutionEngine (detect axiom gaps)
                         →  RegretMemory (evaluate counterfactuals retroactively)
```

---

## Priority for Next Session

### Immediate (wire into pipeline):
1. Wire CouncilReflector into CouncilPhase
2. Wire ErrorAttributionEngine into ActPhase
3. Wire IdentityUtilityEngine into SelectPhase
4. Wire IntrospectionScheduler into main execute loop

### Medium (full integration):
5. Wire TheoryBuilder into ReflectPhase
6. Wire RegretMemory into Select + Act phases
7. Wire AssumptionAuditor into CuriosityDrive

### Deep (proposal → implementation):
8. Full AxiomEvolution with HumanGateway approval
9. Full InterpretationEngine with conflict resolution learning

---

## Files Changed This Session

| Action | File | Purpose |
|--------|------|---------|
| 🗑️ ARCHIVED | `telos/adapters/mealdrama_adapter.py` | Pruned per Prateek's instruction |
| 🗑️ ARCHIVED | `tests/test_mealdrama.py` | Moved with adapter |
| 🗑️ ARCHIVED | `tests/test_meal_messaging.py` | Moved with adapter |
| ✨ CREATED | `telos/core/council/reflector.py` | Council meta-learning |
| ✨ CREATED | `telos/core/meta/error_attribution.py` | Subsystem error attribution |
| ✨ CREATED | `telos/core/curiosity/assumption_auditor.py` | Assumption auditing |
| ✨ CREATED | `telos/core/identity/utility_profiles.py` | Identity utility functions |
| ✨ CREATED | `telos/core/introspection/scheduler.py` | Multi-timescale introspection |
| ✨ CREATED | `telos/core/memory/regret_memory.py` | Counterfactual archival |
| ✨ CREATED | `telos/core/reasoning/theory_builder.py` | Abstraction pipeline |
| ✨ CREATED | `telos/core/axioms/evolution.py` | Axiom proposal system |
| ✨ CREATED | `telos/core/reasoning/interpretation_engine.py` | Principle conflict resolution |
| 🔧 UPDATED | `telos/core/runtime.py` | Wired all 9 components into pipeline |
| 🔧 UPDATED | `telos/AXIOMS.md` | Added v2 extension table |
| 🔧 UPDATED | `telos/GENESIS.md` | Updated architecture state |
| ✨ CREATED | `telos/VISION_v2.md` | This document |
| 📋 CREATED | `archive/mealdrama/` | Archived MealDrama files |
