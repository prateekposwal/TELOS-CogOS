# Integration Plan: RepresentationalLifetime in TELOS

## Proposed Axiom: 6.12 — Representational Lifetime
*Every representation has a measurable lifecycle (birth → growth → plateau → decline → dormant). Death is not deletion — dormant representations retain domain coverage and bridge potential.*

---

## Phase 1: Core Enum & Mixin (New File)

### `telos/core/lifetime/representational_lifetime.py`

```python
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

class RepresentationStage(str, Enum):
    BIRTH = "birth"            # Just formed, high novelty rate
    GROWTH = "growth"          # Rapid prediction gain, expanding coverage
    PLATEAU = "plateau"        # Mature, stable coverage, diminishing returns
    DECLINE = "decline"        # Prediction gain negative, residual growth positive
    DORMANT = "dormant"        # Dead at frontier, alive in bounded domain
    REVIVED = "revived"        # Re-activated via bridge from dormant

@dataclass
class RepresentationHealth:
    novelty_rate: float        # N(t) — new phenomena explained per cycle
    prediction_gain: float     # P(t) — Δaccuracy / Δevidence
    residual_growth: float     # R(t) — unexplained variance change
    coverage: float            # C(t) — fraction of domain explained
    bridge_potential: float    # B(r) — max similarity to active problems

@dataclass
class RepresentationLifecycle:
    """Mixin-level lifecycle tracker for any representational entity."""
    id: str
    stage: RepresentationStage = RepresentationStage.BIRTH
    health: RepresentationHealth = field(default_factory=RepresentationHealth)
    birth_cycle: int = 0
    last_active_cycle: int = 0
    plateau_start_cycle: Optional[int] = None
    decline_start_cycle: Optional[int] = None
    dormant_since_cycle: Optional[int] = None
    domain_boundary: str = ""            # Bounded domain of validity
    revival_triggers: List[str] = field(default_factory=list)  # Conditions for revival
    history: List[Dict[str, Any]] = field(default_factory=list)

    # Health thresholds
    NOVELTY_THRESHOLD: float = 0.01
    PREDICTION_GAIN_THRESHOLD: float = 0.01
    RESIDUAL_GROWTH_THRESHOLD: float = 0.05
    DECLINE_CYCLES_BEFORE_DORMANT: int = 20

    def update_health(self, metrics: Dict[str, float]) -> None:
        """Update health metrics and check stage transitions."""
        ...

    def check_stage_transition(self) -> Optional[RepresentationStage]:
        """
        Evaluate current metrics and return proposed new stage:
        - novelty_rate > threshold → stay in GROWTH
        - prediction_gain ≈ 0 & residual ≈ 0 → PLATEAU
        - residual_growth > 0 for K cycles → DECLINE
        - decline_age > threshold → DORMANT
        - bridge_potential > threshold & dormant → REVIVED
        """
        ...

    def compute_bridge_potential(self, active_representations: List[Any]) -> float:
        """How likely is this dormant representation to connect to active problems?"""
        ...

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "stage": self.stage.value,
            "domain": self.domain_boundary,
            "health": {
                "novelty_rate": self.health.novelty_rate,
                "prediction_gain": self.health.prediction_gain,
                "residual_growth": self.health.residual_growth,
                "coverage": self.health.coverage,
                "bridge_potential": self.health.bridge_potential,
            },
            "history": self.history[-10:],  # last 10 transitions
        }
```

---

## Phase 2: Representation Registry (New File)

### `telos/core/lifetime/representation_registry.py`

```python
class RepresentationRegistry:
    """
    Central registry of all representations across the system.
    Each Theory, Model, Method, Explanation Rule, and Mission gets a
    RepresentationLifecycle attached.
    """

    def __init__(self):
        self._representations: Dict[str, RepresentationLifecycle] = {}

    def register(self, entity_type: str, entity_id: str,
                 domain: str = "", cycle: int = 0) -> RepresentationLifecycle:
        """Register any representational entity with a lifecycle tracker."""
        ...

    def get(self, entity_id: str) -> Optional[RepresentationLifecycle]:
        ...

    def get_dormant(self) -> List[RepresentationLifecycle]:
        """Return all dormant representations with bridge potential > 0."""
        ...

    def get_active(self) -> List[RepresentationLifecycle]:
        """Return all representations in BIRTH/GROWTH/PLATEAU stage."""
        ...

    def get_declining(self) -> List[RepresentationLifecycle]:
        """Return all representations in DECLINE (candidates for archival)."""
        ...

    def cycle_update(self, cycle: int) -> Dict[str, List[str]]:
        """
        Called every cycle. For each representation:
        - Update health metrics (from Observer/collector data)
        - Check stage transition
        - Log transitions
        - Emit events for other subsystems (e.g., curiosity if declining)
        Returns dict of transitions {old_stage: [entity_ids]}.
        """
        ...

    def check_revivals(self, active_problems: List[str]) -> List[str]:
        """
        For dormant representations with high bridge potential to active problems,
        attempt revival by notifying TheoryBuilder / CuriosityDrive.
        """
        ...
```

---

## Phase 3: Integration Points (Existing Files to Modify)

| Existing File | Change |
|---|---|
| `telos/core/reasoning/theory_builder.py` | `Theory` gets a `lifecycle: RepresentationLifecycle` field. `TheoryBuilder.cycle_update()` calls `registry.update_health()` with theory metrics (coverage, prediction accuracy, novelty). |
| `telos/core/reasoning/model_competition.py` | `Model` gets a `lifecycle` field. On `update_probability()`, also update health. When model probability drops below threshold for K cycles, mark as DORMANT (not zero — axiom 4.8 says never fully killed). |
| `telos/core/project/method.py` | `MethodLifecycle` gets mapped to `RepresentationStage` (FAILED → DORMANT, not deletion). `Method` gets bridge_potential field. |
| `telos/core/knowledge/explanation_compression.py` | `RuleStatus.RETIRED` maps to `RepresentationStage.DORMANT`. Retired rules retain coverage statistics for revival check. |
| `telos/core/identity/mission.py` | `MissionLifecycle.DORMANT` already exists — great! Align it with `RepresentationStage.DORMANT`. Add `bridge_potential` and `revival_triggers` to `Mission`. |
| `telos/core/project/substrate.py` | `ProjectLifecycle.STALLED` maps to early DECLINE. `ProjectLifecycle.ARCHIVED` maps to DORMANT. Add health metrics. |
| `telos/core/memory/active_forgetting.py` | `ForgettingCurator` should check `RepresentationLifecycle.stage` before deleting. A representation in DORMANT with bridge_potential > 0 should NOT be deleted — only archived. |
| `telos/core/curiosity/curiosity_drive.py` | Add `DECLINE` and `DORMANT` as curiosity targets. Curiosity should be drawn to declining representations (they have high prediction error) and dormant ones with untested bridge potential. This operationalizes **Axiom 3.6: Curiosity Seeks Broken Models**. |
| `telos/AXIOMS.md` | Add **Axiom 6.12 — Representational Lifetime** to Layer 6. |

---

## Phase 4: Dashboard & Visualization

- Add a **Representation Health** panel to the 3D GridWorld dashboard
- Show a lifecycle waterfall: birth → growth → plateau → decline → dormant for each representation
- Color-code by stage: green (birth/growth) → yellow (plateau) → orange (decline) → blue (dormant) → green flash (revived)
- Show bridge potential as dashed connector lines between dormant representations and active problems

---

## Phase 5: Testing Strategy

| Test | What it validates |
|---|---|
| `test_lifecycle_transitions()` | BIRTH→GROWTH→PLATEAU→DECLINE→DORMANT with synthetic metrics |
| `test_no_premature_deletion()` | DORMANT representations with bridge_potential > 0 persisted after 100 cycles |
| `test_revival()` | Dormant representation revived when bridge_potential exceeds threshold |
| `test_domain_boundary()` | Newton valid in domain "engineering" but dormant in domain "fundamental_physics" |
| `test_curiosity_targets_dormant()` | CuriosityDrive selects dormant repr with high bridge_potential for investigation |
| `test_cross_subsystem()` | Theory, Model, Method, Rule, Mission all register with RepresentationRegistry and report consistent health |

---

## Summary: What Gets Created

```
NEW FILES:
  telos/core/lifetime/__init__.py
  telos/core/lifetime/representational_lifetime.py   (Enum, Health, Lifecycle)
  telos/core/lifetime/representation_registry.py     (Central registry + cycle_update)

MODIFIED FILES:
  telos/core/reasoning/theory_builder.py             (+ lifecycle field)
  telos/core/reasoning/model_competition.py          (+ lifecycle field on Model)
  telos/core/project/method.py                       (+ bridge_potential, DORMANT mapping)
  telos/core/knowledge/explanation_compression.py    (+ RETIRED→DORMANT alignment)
  telos/core/identity/mission.py                     (+ bridge_potential, revival_triggers)
  telos/core/project/substrate.py                    (+ health metrics, STALLED→DECLINE)
  telos/core/memory/active_forgetting.py             (+ lifecycle-aware curator)
  telos/core/curiosity/curiosity_drive.py            (+ DORMANT/DECLINE curiosity targeting)
  telos/AXIOMS.md                                    (+ Axiom 6.12)

TOTAL SCOPE: ~3 new files, ~9 modified files, ~6 new test files
ESTIMATED IMPLEMENTATION: ~400 lines new code, ~150 lines modified
```

---

## Design Principle

> A representation's death is an architectural event, not a memory-management event.  
> The system should mourn — record the plateau, the decline, the domain boundary, the bridge potential —  
> so that when Wiles arrives, Iwasawa is ready.
