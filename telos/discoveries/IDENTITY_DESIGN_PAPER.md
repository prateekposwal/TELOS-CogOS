# Identity as Projection Operator — A Design Paper

**Five Questions Answered**

*REDACTED, responding to the Architect*

---

## Question 1: What is identity? Parameter, constraint, projection, or generator?

**Answer: A projection operator that is also a generator.**

It is NOT a parameter (what TELOS had before — `δC_i` as a penalty term in J). Identity is not a scalar that modulates the optimization. It is the function that restricts the domain of the optimization.

### The Identity Projection Theorem

```
J_I(τ) = argmax_{τ ∈ F(I)} U(τ)
```

where:

```
F(I) = { trajectories τ : τ is compatible with identity I }
```

Identity is a **projection operator** because it projects the space of all possible actions onto the subspace of actions that are *thinkable* for this agent. Actions outside the projection are not scored lower — they are *inadmissible*. They cannot be selected.

Identity is also a **generator** because it generates the admissible space for all lower layers: Identity → generates possible Missions → generates possible Projects → generates possible Methods → generates possible Actions. Each layer is a projection of the one above.

**The difference matters because:** A penalty term can always be overcome if utility is high enough. A projection cannot. You cannot bribe yourself into violating your core identity. "I cannot do this, it isn't me" is structurally different from "I could do this but I'd feel guilty."

---

## Question 2: What remains invariant? What changes at what timescale?

### The 6-Layer Invariance Hierarchy

| Layer | Name | What It Is | Change Rate | Wiles Example |
|-------|------|-----------|-------------|---------------|
| 0 | **Existence** | The system continues to be. | Never changes | Existed before and after FLT |
| 1 | **Identity Core** | Invariant values: curiosity, integrity, truth-seeking, epistemic humility | Almost never | Core curiosity never changed |
| 2 | **Identity Narrative** | Self-description: role, markers, completed missions | Rarely (epochs) | "Number theorist" → "FLT solver" → "Fields medalist" |
| 3 | **Mission** | Strategic purpose: what the system is trying to achieve | Rarely (years) | "Advance mathematics" |
| 4 | **Project** | Concrete instantiation of mission: the specific problem | Occasionally (months) | "Prove Fermat's Last Theorem" |
| 5 | **Methods** | Techniques used within a project | Often (weeks/days) | Iwasawa → FAIL → Galois → SUCCESS |
| 6 | **Actions** | Individual decisions | Constantly (per cycle) | Every mathematical step |

### The Invariance Principle

Each layer is an invariant for all layers below it.

- Identity Core is invariant for Narrative: you cannot adopt a narrative that violates Core.
- Narrative is invariant for Missions: you cannot pursue a mission that your narrative cannot generate.
- Mission is invariant for Projects: projects serve the mission.
- Project is invariant for Methods: methods serve the project.
- Method is invariant for Actions: actions implement the method.

This is not a speed hierarchy (though speed follows). It is a **containment hierarchy**:

```
Identity Core ⊃ Narrative ⊃ Missions ⊃ Projects ⊃ Methods ⊃ Actions
```

Each layer *contains* the admissible space for the next. Change is slow at the top because changing a layer would reconfigure everything it contains.

---

## Question 3: How does identity generate missions rather than merely influence choices?

### The Identity Cascade

Identity does NOT rank missions (that would be filtering). Identity GENERATES missions (this is generation).

```
Identity Core
    │
    │  generates the space of thinkable self-descriptions
    ▼
Identity Narrative
    │
    │  generates the space of pursuable missions
    ▼
Missions
    │
    │  generate the space of viable projects
    ▼
Projects
    │
    │  generate the space of applicable methods
    ▼
Methods
    │
    │  generate the space of executable actions
    ▼
Actions
```

### Formal statement

```
Let I = Identity Core (frozen)
Let N = Identity Narrative (evolves)

M(I, N) = { m : m is a mission that could be pursued by someone
               with core values I and self-description N }

P(m) = { p : p is a project that serves mission m }

Mtd(p) = { t : t is a method applicable to project p }

A(t) = { a : a is an action implementing method t }
```

Every action `a` is connected through four generative layers back to identity:

```
a ∈ A(t) ⊆ Mtd(p) ⊆ P(m) ⊆ M(I, N) ⊆ N(I)
```

If any link breaks, the action is **inadmissible**. It cannot be selected by `J_I(τ)`.

### Why this is NOT filtering

Filtering says: "Generate all possible actions, then rank by identity-compatibility."

Generation says: "Identity determines which actions are even thinkable. The ones outside the projection are not evaluated — they are absent from the option space."

This is the difference between telling a mathematician "you could steal the proof, but that would violate your integrity" (filtering, penalty) and "it literally does not occur to you to steal the proof — that action doesn't exist in your space" (generation, projection).

---

## Question 4: How does an agent retire or transform a mission without losing continuity of identity?

### Mission Death + Rebirth Cycle

When a mission completes (Wiles proved FLT), the system must not become directionless. The cycle is:

```
Phase 0: Identity Core (unchanged throughout)

Phase 1: Mission Completion Detection
    ↓  (all projects completed, or mission explicitly terminated)

Phase 2: Reflection
    - What did we learn?
    - What capabilities were developed?
    - What remains unresolved?
    ↓

Phase 3: Identity Narrative Update
    - Core remains unchanged
    - Narrative records: "veteran_of_{completed_mission}"
    - Compression distills mission experience into narrative markers
    ↓

Phase 4: New Mission Generation
    - Identity Core + updated Narrative → generates candidate missions
    - Mission Arbiter selects from candidates
    ↓

Phase 5: New Project Creation
    - Selected mission spawns projects
    - New methods and actions follow
```

### Continuity of Identity

Identity Core never changes during this cycle. The *person* who proved FLT is the same person who started. The Narrative updates (mathematician → FLT solver → mentor) but Core persists: curiosity, integrity, truth-seeking.

This is why `IdentityCore` is a frozen dataclass at `telos/core/identity/system_self.py` — it cannot be modified by the ψ operator. It can only be changed through Axiom Evolution (axiom 5.2) with HumanGateway approval.

### Three-Level Abandonment

Per `telos/core/project/rational_abandonment.py`:

| Level | Abandonment Type | Threshold | What Preserves Identity |
|-------|-----------------|-----------|------------------------|
| Method | Pivot | 5 cycles of failure | Project continues unchanged |
| Project | Archive | 50 cycles of stagnation | Mission continues, narrative records failure |
| Mission | Complete/Fail | 500+ cycles or explicit completion | Narrative updates, Core persists |

---

## Question 5: If multiple missions conflict, how are they arbitrated?

### Mission Arbitration

Per `telos/core/identity/mission_arbitration.py`, arbitration operates on four axes:

| Axis | Weight | What It Measures |
|------|--------|-----------------|
| Core Alignment | 40% | How well does this mission express Identity Core values? (non-negotiable floor) |
| Urgency | 25% | Does this mission have a deadline or window of opportunity? |
| Priority | 20% | What is the intrinsic importance of this mission? |
| Inertia | 15% | What is the cost of switching from the currently active mission? |

### Arbitration Protocol

1. **Filter**: Missions with Core Alignment below threshold (≤ 0.3) are excluded entirely. Violating Core is not a trade-off — it's an identity crisis.
2. **Score**: Weighted combination of the four axes.
3. **Rank**: Highest score → becomes active. Others → dormant.
4. **Dormant missions stay in the portfolio**. They can be reactivated. They are not deleted.
5. **Re-arbitration triggers**: (a) new mission generated, (b) active mission completes/fails, (c) periodic re-evaluation.

### What Arbitration is NOT

Arbitration does NOT eliminate missions. It does NOT say "this mission is bad." It says "this mission is not the priority *right now*." All missions remain in the `MissionPortfolio` with their full lifecycle state.

---

## Connecting the Dots: The Identity Pattern

The five answers reveal a single coherent pattern:

> **Identity is not part of the decision. Identity is what makes the decision possible.**

Every optimization algorithm needs an objective function and a feasible set. In TELOS, the objective function changes per cycle (J(τ) with its 18 terms), but the feasible set is determined by identity. Identity answers: "What problems am I allowed to solve? What actions are conceivable for me?"

This is the transition from **Decision Theory** to **Purpose Theory**:

| Decision Theory | Purpose Theory |
|----------------|----------------|
| Which action maximizes utility? | Why does this optimization exist? |
| Identity is a cost term | Identity is a projection operator |
| All actions are on the table | Only admissible actions are thinkable |
| Optimization finds the best | Projection defines the possible |
| The frame is chosen | The frame is constitutive |

The six-layer hierarchy, the identity cascade, the projection gate, mission arbitration, and the death+rebirth cycle are all expressions of a single principle: **identity supplies the objective for the optimization rather than being a term within it**.

### What Remains to Connect

| Concept | Status | File |
|---------|--------|------|
| Identity Core | ✅ Implemented | `system_self.py` |
| Identity Narrative | ✅ Implemented | `system_self.py` |
| Identity Projection Gate | ✅ Implemented | `commitment_optimizer.py` |
| Mission entity | ✅ Implemented | `identity/mission.py` |
| Mission Arbitration | ✅ Implemented | `identity/mission_arbitration.py` |
| Mission Death + Rebirth | ✅ Implemented | `identity/mission_lifecycle.py` |
| Project Substrate | ✅ Implemented | `project/substrate.py` |
| Rational Abandonment | ✅ Implemented | `project/rational_abandonment.py` |
| Strategic Coherence | ✅ Implemented | `project/strategic_coherence.py` |
| Methods layer | ✅ Implemented | `project/method.py` |
| Aesthetic Heuristic | ✅ Implemented | `commitment_optimizer.py` |
| F(I) in select.py | ✅ Implemented | `phases/select.py` |
| **Design paper** | ✅ **THIS DOCUMENT** | `discoveries/IDENTITY_DESIGN_PAPER.md` |
| Representational Lifetime | 📄 Planned | `discoveries/REPRESENTATIONAL_LIFETIME_PLAN.md` |
| End-to-end integration test | ✅ Done | `tests/core/test_pipeline_integration.py` |

The identity architecture is now fully documented. The five questions are answered. The dots are connected.
