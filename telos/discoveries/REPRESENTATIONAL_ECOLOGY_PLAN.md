# Integration Plan: Representational Ecology in TELOS

## Proposed Axiom: 6.12 — Representational Ecology
*Representations form an ecological system. They compete for niche dominance, specialize into bounded domains, bridge across disconnected territories, and when exhausted, decompose into nutrients that seed new representations. Exhaustion is not falsehood — a representation may be perfectly valid within its niche yet no longer productive at the frontier.*

---

## Philosophical Shift: Lifecycle -> Ecology

The earlier plan proposed `RepresentationLifecycle` as a linear stage manager: every entity gets a birth-to-dormant tracker. The ecology approach is fundamentally different:

| Dimension | Lifecycle Approach | Ecology Approach |
|---|---|---|
| **Unit of analysis** | Individual representation | Relationships between representations |
| **Core question** | "Is this representation still alive?" | "Is this representation still productive in this niche?" |
| **End state** | Death/Dormancy | Decomposition into nutrients |
| **Relationships** | Unrelated (independent arcs) | Competition, symbiosis, predation, bridging |
| **Forgetting** | Delete or archive | Decompose into reusable components |
| **Success metric** | Longevity | Nutrient release rate, bridge count, specialization depth |
| **Key mechanism** | Stage transitions | Ecological interactions (competition, bridging, decomposition) |
| **Architectural pattern** | Observer + Enum + Registry | Ecosystem manager + Niche map + Nutrient cycle |

---

## New Module: `telos/core/ecology/`

### File Structure

```
telos/core/ecology/
    __init__.py
    representational_ecology.py    # EcoRepresentation, Niche, EcologicalRole enums
    ecology_manager.py             # EcologyManager — the ecosystem tracker
```

---

## Phase 1: Core Data Model (New File)

### `telos/core/ecology/representational_ecology.py`

```python
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from datetime import datetime


class EcologicalRole(str, Enum):
    """The role a representation plays in the cognitive ecosystem."""
    KEYSTONE = "keystone"       # Enables many other representations
    CANOPY = "canopy"           # Dominant paradigm in a broad niche
    BRIDGE = "bridge"           # Connects otherwise isolated domains
    SPECIALIST = "specialist"   # Optimal within a narrow boundary
    PIONEER = "pioneer"         # New representation in a sparse ecosystem
    HYBRID = "hybrid"           # Formed from merger of two representations
    DECOMPOSER = "decomposer"   # Works on breaking down exhausted theories
    PARASITE = "parasite"       # Mimics productive repr but generates no MKG


class NicheRelation(str, Enum):
    """How two representations relate within a niche."""
    COMPETING = "competing"         # Same niche, zero-sum
    SYMBIOTIC = "symbiotic"         # Mutual benefit
    BRIDGED = "bridged"             # Connected across domains
    PREDATORY = "predatory"         # One consumes the other's nutrients
    NEUTRAL = "neutral"             # No significant interaction
    SPECIALIZED = "specialized"     # Adjacent niches, minimal overlap


@dataclass
class Niche:
    """A bounded domain where representations operate.

    A niche is defined by:
    - domain: the subject area (e.g., "orbital_mechanics", "number_theory")
    - boundary_params: specific conditions where a repr is optimal
    - occupancy: which representations currently occupy this niche
    - saturation: how crowded the niche is (0-1)
    """
    id: str
    name: str
    domain: str
    boundary_params: Dict[str, Any] = field(default_factory=dict)
    occupied_by: List[str] = field(default_factory=list)  # repr IDs
    saturation: float = 0.0
    marginal_discovery_rate: float = 0.0  # Average MKG across occupants

    def compute_overlap(self, other: Niche) -> float:
        """Jaccard-like similarity between niches."""
        keys_self = set(self.boundary_params.keys())
        keys_other = set(other.boundary_params.keys())
        if not keys_self and not keys_other:
            return 0.0
        intersection = len(keys_self & keys_other)
        union = len(keys_self | keys_other)
        return intersection / max(union, 1)


@dataclass
class EcoRepresentation:
    """A representation as an organism in the cognitive ecosystem.

    Replaces the older RepresentationLifecycle model. Instead of a
    linear stage, the EcoRepresentation has:
    - birth_time: when it speciated
    - maturity: how developed the representation is (0-1)
    - exploration_depth: how many layers deep it has been pushed
    - bridge_count: how many cross-domain connections it maintains
    - residual_error: unexplained variance at its frontier
    - stagnation_score: cycles since last novel prediction
    - retirement_probability: likelihood it should be retired from frontier
    - marginal_knowledge_gain: return on thinking investment
    - niche_boundary: the precise domain boundary
    - nutrient_profile: what this representation will release when it decomposes
    """
    id: str
    name: str
    description: str
    role: EcologicalRole = EcologicalRole.SPECIALIST
    source_type: str = ""  # e.g., "theory", "model", "method", "rule"

    # Birth & lineage
    birth_time: float = 0.0
    parent_ids: List[str] = field(default_factory=list)  # representations this speciated from
    child_ids: List[str] = field(default_factory=list)    # representations that speciated from this

    # Maturity & exploration
    maturity: float = 0.0           # 0=seed, 0.5=sapling, 1.0=mature tree
    exploration_depth: int = 0      # How many implication layers explored

    # Ecological metrics
    bridge_count: int = 0           # Number of active cross-domain connections
    bridge_targets: List[str] = field(default_factory=list)  # Domains bridged to
    residual_error: float = 0.0     # Unexplained variance at frontier
    stagnation_score: float = 0.0   # Cycles since last novel prediction

    # Frontier metrics
    marginal_knowledge_gain: float = 1.0  # MKG(t) — return on thinking
    representational_capacity: float = 1.0  # RC(r) — domain coverage * depth
    remaining_potential: float = 1.0  # Prem(r) — untapped frontier
    retirement_probability: float = 0.0  # Rprob — likelihood of frontier retirement

    # Niche
    niche_id: str = ""
    niche_boundary: Dict[str, Any] = field(default_factory=dict)

    # Decomposition / nutrient tracking
    is_decomposing: bool = False
    decomposition_progress: float = 0.0  # 0=None, 1=Fully decomposed
    nutrient_profile: Dict[str, float] = field(default_factory=dict)
    # e.g., {"techniques": 0.7, "lemmas": 0.2, "counterexamples": 0.1}

    def update_metrics(self, new_mkg: float, new_stagnation: int,
                       new_bridges: int) -> None:
        """Update frontier metrics and optionally trigger decomposition."""
        self.marginal_knowledge_gain = new_mkg
        self.stagnation_score = new_stagnation
        self.bridge_count = new_bridges

        # Update remaining potential based on MKG trend
        self.remaining_potential = max(0.0,
            self.marginal_knowledge_gain * (1.0 + self.bridge_count * 0.1)
            - self.stagnation_score * 0.05)

        # Update retirement probability
        if self.marginal_knowledge_gain < 0.01 and self.stagnation_score > 10:
            self.retirement_probability = min(1.0,
                self.retirement_probability + 0.1 * (1.0 / max(self.bridge_count, 1)))

    def should_decompose(self) -> bool:
        """Check if this representation is a candidate for nutrient release."""
        return (self.retirement_probability > 0.8
                and self.marginal_knowledge_gain < 0.001
                and self.stagnation_score > 20)

    def compute_nutrient_profile(self) -> Dict[str, float]:
        """Calculate what nutrients this repr will release on decomposition.

        Different roles release different nutrient mixes:
        - Keystone: high structural axioms, low techniques
        - Specialist: high techniques, low axioms
        - Bridge: high connection patterns, medium axioms
        """
        if self.role == EcologicalRole.KEYSTONE:
            return {"axioms": 0.5, "techniques": 0.3, "connections": 0.2}
        elif self.role == EcologicalRole.SPECIALIST:
            return {"techniques": 0.7, "lemmas": 0.2, "boundary_conditions": 0.1}
        elif self.role == EcologicalRole.BRIDGE:
            return {"connections": 0.6, "translations": 0.3, "axioms": 0.1}
        else:
            return {"techniques": 0.4, "lemmas": 0.3, "axioms": 0.2,
                    "counterexamples": 0.1}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role.value,
            "source_type": self.source_type,
            "maturity": self.maturity,
            "exploration_depth": self.exploration_depth,
            "bridge_count": self.bridge_count,
            "marginal_knowledge_gain": self.marginal_knowledge_gain,
            "stagnation_score": self.stagnation_score,
            "retirement_probability": self.retirement_probability,
            "remaining_potential": self.remaining_potential,
            "niche_id": self.niche_id,
            "is_decomposing": self.is_decomposing,
            "decomposition_progress": self.decomposition_progress,
            "parent_ids": self.parent_ids,
            "child_ids": self.child_ids,
        }


@dataclass
class EcosystemSnapshot:
    """A snapshot of the entire cognitive ecosystem at a point in time."""
    cycle: int
    representation_count: int
    active_count: int
    decomposing_count: int
    dormant_count: int

    # Ecosystem health metrics
    diversity: float
    competition_intensity: float
    bridge_density: float
    nutrient_cycling_rate: float
    ecosystem_maturity: float

    dominant_roles: Dict[str, int]  # role -> count
    saturated_niches: List[str]
    top_bridges: List[str]  # repr IDs with highest bridge count
```

---

## Phase 2: Ecology Manager (New File)

### `telos/core/ecology/ecology_manager.py`

```python
class EcologyManager:
    """
    Tracks the ecosystem of representations across all subsystems.

    Responsibilities:
    1. Register new representations (from TheoryBuilder, ModelCompetition, etc.)
    2. Track ecological interactions (competition, symbiosis, bridging)
    3. Compute ecosystem health metrics (diversity, nutrient cycling rate)
    4. Detect niche saturation and competition intensity
    5. Trigger decomposition of exhausted representations
    6. Route released nutrients as building blocks for new representations
    7. Maintain nutrient archive (decomposed representations with their profiles)

    Key difference from the lifecycle approach:
    - Representations don't just die — they decay into nutrients
    - Nutrients feed new representations (Kintsugi principle applied to ideas)
    - The ecosystem has emergent properties (diversity, maturity) not visible
      from individual representations
    """

    def __init__(self, decomposition_threshold: float = 0.8,
                 niche_overlap_threshold: float = 0.6):
        self._representations: Dict[str, EcoRepresentation] = {}
        self._niches: Dict[str, Niche] = {}
        self._nutrient_archive: Dict[str, Dict] = {}
        # Maps: domain -> [(repr_id, similarity)]
        self._bridge_map: Dict[str, List[tuple]] = {}
        self._snapshots: List[EcosystemSnapshot] = []
        self._cycle: int = 0

    # --- Registration ---

    def register(self, repr_id: str, name: str, description: str,
                 source_type: str = "",
                 role: EcologicalRole = EcologicalRole.PIONEER,
                 niche_id: str = "",
                 parent_ids: Optional[List[str]] = None,
                 nutrient_profile: Optional[Dict[str, float]] = None) -> str:
        """Register a new representation in the ecosystem."""
        ...

    def register_niche(self, niche_id: str, name: str, domain: str,
                       boundary_params: Dict[str, Any]) -> Niche:
        """Register or update a niche."""
        ...

    # --- Ecosystem Dynamics ---

    def compute_competition(self, niche_id: str) -> float:
        """
        Competition intensity within a niche.
        High when many representations with high overlap compete for the same niche.
        Uses pairwise NicheRelation.COMPETING scoring.
        """
        ...

    def compute_diversity(self) -> float:
        """
        Ecosystem diversity = number of occupied niches /
        sum of similarity between all niche pairs.
        High diversity = many distinct, non-overlapping niches.
        """
        ...

    def detect_saturation(self, niche_id: str) -> float:
        """
        How saturated a niche is.
        Saturated = high competition + low marginal discovery rate.
        Triggers: representations in this niche should specialize or bridge.
        """
        ...

    def find_bridge_opportunities(self, repr_id: str) -> List[str]:
        """
        Find other representations that could be bridged to this one.
        Uses niche boundary similarity + unexplored adjacency.
        Returns list of repr_ids with high bridging potential.
        """
        ...

    # --- Nutrient Cycling ---

    def trigger_decomposition(self, repr_id: str) -> Dict[str, float]:
        """
        Convert an exhausted representation into nutrients.

        Process:
        1. Compute nutrient profile from the representation's role + content
        2. Move representation to decomposing state
        3. Release nutrients into the ecosystem (available for new reprs)
        4. Archive the decomposed representation with its nutrient profile
        5. Remove from active competition pool

        Returns the nutrient profile released.
        """
        ...

    def get_available_nutrients(self, domain: str = "") -> Dict[str, float]:
        """
        Get all currently available nutrients in the ecosystem.
        If domain specified, filter nutrients relevant to that domain.
        These nutrients can seed new representations via TheoryBuilder.
        """
        ...

    def spawn_from_nutrients(self, domain: str, seed_name: str,
                             nutrient_sources: List[str]) -> str:
        """
        Create a new representation from available nutrients.
        - Combines nutrient profiles from multiple decomposed representations
        - Assigns PIONEER role
        - Sets parent_ids to the decomposed source representations
        This operationalizes Kintsugi: the new representation is formed
        from the cracks and remains of exhausted ones.
        """
        ...

    # --- Bridging ---

    def register_bridge(self, repr_a: str, repr_b: str,
                        bridge_strength: float = 0.5) -> None:
        """Register a cross-domain bridge between two representations."""
        ...

    def get_bridge_candidates(self, domain: str) -> List[EcoRepresentation]:
        """Find dormant representations with high bridge potential to a domain."""
        ...

    # --- Queries ---

    def get_active(self) -> List[EcoRepresentation]:
        """Representations not yet decomposing."""
        ...

    def get_decomposing(self) -> List[EcoRepresentation]:
        """Representations currently undergoing decomposition."""
        ...

    def get_dormant(self) -> List[EcoRepresentation]:
        """Representations with MKG near zero but not yet decomposing."""
        ...

    def get_high_bridge_count(self, min_bridges: int = 3) -> List[EcoRepresentation]:
        """Return the most connected representations."""
        ...

    # --- Cycle Update ---

    def cycle_update(self, cycle: int) -> EcosystemSnapshot:
        """
        Called every cycle. For each representation:
        1. Update metrics (MKG, stagnation, bridges) from collector data
        2. Check for saturation in niches
        3. Check for decomposition candidates
        4. Check for bridge opportunities
        5. Process any completed decompositions -> nutrients released
        6. Take ecosystem snapshot
        """
        ...

    # --- Persistence ---

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the entire ecosystem state."""
        ...

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EcologyManager:
        """Restore ecosystem state from serialized data."""
        ...
```

---

## Phase 3: Integration Points (Existing Files to Modify)

### Theory Changes

| Existing File | Change Required | Specifics |
|---|---|---|
| `telos/core/reasoning/theory_builder.py` | `Theory` gets an `ecology: EcoRepresentation` field. `TheoryBuilder` registers new theories with `EcologyManager`. On cycle update, push MKG metrics to ecology. When a hypothesis is falsified, it's not deleted — it's flagged for potential decomposition. | `Theory` class: add `ecology_id: str = ""`. `TheoryBuilder.__init__`: accept optional `ecology_manager`. `_promote_to_theory()`: call `ecology_manager.register()`. |
| `telos/core/reasoning/model_competition.py` | `Model` gets an `ecology: EcoRepresentation` field. On `retire_weakest_model()`, instead of deleting, call `ecology_manager.trigger_decomposition()`. The probability floor prevents zero, but if probability == min_probability for K cycles, the model is exhausted and should release nutrients. | `Model` class: add `ecology_id: str = ""`. `ModelCompetition.__init__`: accept optional `ecology_manager`. `retire_weakest_model()`: call `ecology_manager.trigger_decomposition()`. |
| `telos/core/project/method.py` | `MethodLifecycle.FAILED` maps to ecological DECOMPOSITION, not just a terminal state. `Method` gets `EcoRepresentation` fields (bridge_count, stagnation_score). `FAILED` methods should have their techniques extracted as nutrients. | `Method` class: add `bridge_potential: float = 0.0`, `ecology_id: str = ""`. `MethodRegistry`: accept optional `ecology_manager`. On `record_attempt()` with FAILED transition, call `ecology_manager.trigger_decomposition()`. |
| `telos/core/knowledge/explanation_compression.py` | `RuleStatus.RETIRED` maps to ECOLOGY_DORMANT or DECOMPOSING. Retired rules retain coverage statistics for nutrient cycling. | Add `ecology_id` to compressed rules. On retirement, register with ecology manager as decomposing. |
| `telos/core/identity/mission.py` | `MissionLifecycle.DORMANT` aligns with ecological dormancy (not decomposition). Add `bridge_potential` and `revival_triggers` to `Mission`. | Map DORMANT missions to `EcoRepresentation` with role=SPECIALIST. Missions have high remaining potential when bridged. |
| `telos/core/project/substrate.py` | `ProjectLifecycle.STALLED` maps to early exhaustion signal. `ARCHIVED` maps to decomposition-ready. | On ARCHIVE, call `ecology_manager.trigger_decomposition()` if the project's representations are exhausted. |
| `telos/core/memory/active_forgetting.py` | `ForgettingCurator` should check `EcoRepresentation.retirement_probability` before deleting. A representation with high bridge_count or low retirement_probability should NOT be deleted — only archived for nutrient cycling. | In `curate()`, check `is_bridge_candidate(repr_id)` before eviction. |
| `telos/core/curiosity/curiosity_drive.py` | Add `DECOMPOSING` and `DORMANT` as curiosity targets. Curiosity should be drawn to: (1) decomposing representations with nutrient profiles that could seed new theories, (2) dormant representations with untested bridge potential, (3) niches with high saturation (need for speciation). This operationalizes **Axiom 3.6: Curiosity Seeks Broken Models**. | `CuriosityDrive.compute_curiosity()`: add factors for nutrient potential, bridge potential, niche saturation. Score: `C = alpha*MKG + beta*niche_saturation + gamma*bridge_potential`. |
| `telos/AXIOMS.md` | Add **Axiom 6.12 — Representational Ecology** to Layer 6. | See proposed axiom text at top of this document. |

### Integration Architecture

```
                    +------------------+
                    |  EcologyManager  |
                    |  (tracks all)    |
                    +--------+---------+
                             |
         +-------------------+-------------------+
         |                   |                   |
    +----v-----+       +----v-----+       +-----v----+
    | Theory   |       | Model    |       | Method   |
    | Builder  |       | Compet.  |       | Registry |
    +----------+       +----------+       +----------+
         |                   |                   |
    Theories have       Models have         Methods have
    EcoRepresentation   EcoRepresentation   bridge_potential
    registered with     registered with     and can release
    ecology on birth    ecology on birth    nutrients on FAIL

    +----------+       +----------+       +----------+
    |Forgetting|       | Curiosity|       | Council  |
    |Curator   |       | Drive    |       | Validator|
    +----------+       +----------+       +----------+
    Checks repr        Targets:           Checks:
    retirement_prob    decomposing,       ecosystem health
    before eviction    dormant reprs      diversity metric
```

---

## Phase 4: Dashboard & Visualization

- Add an **Ecosystem Health** panel to the 3D GridWorld dashboard
- Species map: show active representations as organisms in a 2D niche space
  - X-axis: domain
  - Y-axis: maturity
  - Size: representational capacity
  - Color: ecological role
  - Connector lines: bridges (dashed = weak, solid = strong)
- Nutrient pool visualization: glowing particles moving from decomposing representations to new ones
- Ecosystem health gauges: diversity, competition intensity, nutrient cycling rate
- Decomposition animation: when a representation exhausts, it "crumbles" into particles that drift to new representations
- Kintsugi highlight: when a new representation spawns from nutrients, show the parent cracks visibly incorporated

---

## Phase 5: Testing Strategy

| Test | What it validates |
|---|---|
| `test_eco_register_and_bridge()` | Register two representations, create a bridge, verify bridge_count incremented on both |
| `test_competition_intensity()` | Two representations in the same niche -> high competition intensity; different niches -> low |
| `test_decomposition_releases_nutrients()` | Trigger decomposition on an exhausted representation -> nutrients appear in get_available_nutrients() |
| `test_spawn_from_nutrients()` | Spawn a new representation from decomposed nutrients -> parent_ids reference the original decomposed reprs |
| `test_no_premature_decomposition()` | A representation with high MKG or high bridge_count returns False from should_decompose() |
| `test_ecosystem_snapshot()` | cycle_update() produces a valid EcosystemSnapshot with diversity, maturity, bridge_density |
| `test_mkg_collapse_triggers_retirement()` | Feed declining MKG values -> retirement_probability increases -> eventually triggers decomposition |
| `test_bridge_detection()` | EcoRepresentation with bridge_count=0 in high-saturation niche -> find_bridge_opportunities returns candidates |
| `test_niche_overlap()` | Two niches with similar boundary_params have high compute_overlap() |
| `test_cross_subsystem_integration()` | TheoryBuilder, ModelCompetition, MethodRegistry all register with the same EcologyManager and report consistent state |

---

## Phase 6: Nutrient Cycle — Complete Flow

Here is the full lifecycle of a representation in the ecology (contrast with the linear lifecycle):

```
BIRTH (Speciation):
  1. A new insight forms from:
     a) A nutrient released by a decomposed representation
     b) A bridge between two dormant representations
     c) Direct observation (raw experience -> theory)
  2. EcologyManager.register() called with role=PIONEER
  3. Assigned to a niche based on domain boundary

GROWTH (Niche Expansion):
  1. Exploration depth increases as the representation is applied
  2. Bridges form to adjacent domains (register_bridge)
  3. MKG is high; remaining potential is high
  4. Role may shift (PIONEER -> CANOPY or SPECIALIST)

MATURITY (Canopy Dominance / Specialization):
  1. MKG begins to decline as the frontier is reached
  2. Competition detected in niche -> compute_competition()
  3. Representation either:
     a) Specializes (narrows niche boundary) -> role = SPECIALIST
     b) Competes (stays in niche, drives refinement)
     c) Bridges (finds cross-domain connections) -> role = BRIDGE

EXHAUSTION (Frontier Reached):
  1. MKG -> 0 for threshold cycles
  2. stagnation_score increases
  3. retirement_probability rises
  4. remaining_potential approaches 0
  5. Key check: is the representation still productive in ANY niche?
     -> If yes: domain-shift, not decomposition
     -> If no: proceed to decomposition

DECOMPOSITION (Nutrient Release):
  1. should_decompose() returns True
  2. compute_nutrient_profile() extracts:
     - Techniques (methods, algorithms, procedures)
     - Lemmas (proven results, intermediate steps)
     - Axioms (underlying assumptions, structural principles)
     - Counterexamples (boundary cases the repr couldn't handle)
     - Connections (bridge patterns to other domains)
  3. Nutrients released into ecosystem pool
  4. Decomposed representation archived with full nutrient profile

NUTRIENT CYCLING (Seeding New Representations):
  1. TheoryBuilder queries get_available_nutrients()
  2. A new theory forms using techniques from decomposed repr A,
     lemmas from decomposed repr B, and axioms from repr C
  3. Kintsugi pattern: the new representation carries the cracks
     of its predecessors (parent_ids, inherited boundary conditions)
  4. The cycle continues
```

---

## Summary: What Gets Created

```
NEW FILES:
  telos/core/ecology/__init__.py
  telos/core/ecology/representational_ecology.py   (EcoRepresentation, Niche, EcologicalRole)
  telos/core/ecology/ecology_manager.py            (EcologyManager + EcosystemSnapshot)

MODIFIED FILES:
  telos/core/reasoning/theory_builder.py           (+ ecology_id on Theory, register with EcologyManager)
  telos/core/reasoning/model_competition.py        (+ ecology_id on Model, decomposition on retire)
  telos/core/project/method.py                     (+ bridge_potential, ecology_id, FAILED->decomposition)
  telos/core/knowledge/explanation_compression.py  (+ RETIRED->DECOMPOSING alignment)
  telos/core/identity/mission.py                   (+ bridge_potential, revival_triggers)
  telos/core/project/substrate.py                  (+ exhaustion signals, ARCHIVED->decomposition)
  telos/core/memory/active_forgetting.py           (+ retirement_probability check in curator)
  telos/core/curiosity/curiosity_drive.py          (+ DECOMPOSING/DORMANT targeting, niche saturation)
  telos/AXIOMS.md                                  (+ Axiom 6.12 — Representational Ecology)

REMOVED FILES:
  telos/core/lifetime/                             (entire directory — replaced by ecology/)

TOTAL SCOPE: ~3 new files, ~9 modified files, ~1 removed directory, ~10 new test files
ESTIMATED IMPLEMENTATION: ~550 lines new code, ~180 lines modified
```

---

## Design Principles

1. **Exhaustion is not falsehood.** A representation can be perfectly correct within its niche but no longer productive at the frontier. The system should honor both truths simultaneously.

2. **Decomposition is not deletion.** When a representation exhausts, it should be archived with full nutrient profile so that its components can seed new representations. Kintsugi — the cracks make the next thing stronger.

3. **Ecosystem > individual.** The health of the ecosystem (diversity, nutrient cycling rate, bridge density) is a first-class metric. A system with high ecosystem diversity recovers faster from paradigm shifts.

4. **Bridges are the most valuable representations.** A representation with high bridge count (connecting otherwise isolated niches) has the lowest retirement probability and should be preserved even when its own MKG is low. Bridges are the neural pathways of the cognitive ecosystem.

5. **Let ideas speak in their own voice.** The ecology does not impose a single truth metric. Different roles (keystone, specialist, bridge) are evaluated on different criteria. A specialist is not a failed canopy; it is a different kind of organism.

---

> *A representation's exhaustion is not the end of its story — it is the beginning of the next representation's first chapter.*
