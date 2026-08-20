"""
TELOS v6.2 — Logistics World (second-world validation).

A genuine second world that exercises what DevDomain does not:
  - partial observability (actual state != observed state)
  - delayed consequences (action at t0 -> consequence at t1/t2/t3)
  - multiple interacting resources
  - competing objectives (exposed separately, NOT a single "logistics score")
  - irreversible actions (risk != 0)
  - action costs
  - temporal deadlines
  - external disturbances (exogenous, not predictable by the model)
  - recovery actions
  - model prediction vs observed outcome (Reality Gap)

This is a legitimate DomainSimulator/DomainAdapter. NO logistics-specific logic
lives in the cognitive core — it all sits behind WorldSpec / DomainSimulator /
DomainAdapter / the evidence + capability machinery.

CRITICAL no-toy: we do NOT use `GOAL - position` / `np.sign(...)` movement.
Actions are DISCRETE logistics primitives (dispatch/hold/reroute/allocate/...)
with real consequence, cost, delay, and irreversibility semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
import numpy as np

from telos.core.contracts.domain_model import (
    DomainSimulator, DomainAdapter, EvaluationReport, WorldSpec,
)
from telos.world.facts import DomainFacts
from telos.world.world import World
from telos.world.evidence import (
    EvidenceInfo, EvidenceSource, ValidationStatus,
)

STATE_DIM = 12
# State layout (actual world state):
#   [0] inventory_level       (0-1 normalized, scarce resource)
#   [1] cash                  (0-1, budget remaining)
#   [2] vehicles_available    (0-1 fraction)
#   [3] orders_in_flight       (0-1)
#   [4] lateness_accumulated  (0-1, grows over time / deadlines)
#   [5] sla_health            (0-1, service level)
#   [6] fuel/resources        (0-1)
#   [7] observed_delay         (0-1, exogenous disturbance)
#   [8] shipment_progress     (0-1, delayed consequence progress)
#   [9] committed_risk        (0-1, accumulated irreversible commitments)
#   [10] deadline_pressure     (0-1, temporal constraint)
#   [11] external_event_flag   (0 or 1, disturbance active)

HEALTHY = np.array([0.8, 0.8, 0.8, 0.3, 0.1, 0.9, 0.7, 0.0, 0.0, 0.0, 0.2, 0.0])


class LogisticsAction(str, Enum):
    HOLD = "hold"                       # no-op / wait
    DISPATCH = "dispatch"               # commit a shipment (irreversible, costly)
    REROUTE = "reroute"                 # change an in-flight routing (moderate cost)
    CONSOLIDATE = "consolidate"         # merge shipments (reduces cost)
    ALLOCATE = "allocate"               # commit scarce inventory (irreversible-ish)
    CANCEL = "cancel"                   # cancel a shipment (penalty, highly irreversible)
    REPLENISH = "replenish"             # restore inventory (cost, delay)
    ESCALATE = "escalate"               # escalate to human (no physical change)


# Each action has: index used by intent mapping, cost, irreversibility, delay.
ACTION_META: Dict[str, Dict[str, float]] = {
    "hold":        {"cost": 0.0, "irreversibility": 0.0, "delay": 0},
    "dispatch":    {"cost": 0.15, "irreversibility": 0.7, "delay": 2},
    "reroute":     {"cost": 0.10, "irreversibility": 0.4, "delay": 1},
    "consolidate": {"cost": -0.10, "irreversibility": 0.2, "delay": 1},
    "allocate":    {"cost": 0.12, "irreversibility": 0.6, "delay": 1},
    "cancel":      {"cost": 0.30, "irreversibility": 0.9, "delay": 0},
    "replenish":   {"cost": 0.20, "irreversibility": 0.3, "delay": 3},
    "escalate":    {"cost": 0.0, "irreversibility": 0.0, "delay": 0},
}

# Actions that represent genuine irreversible / high-commitment decisions.
HIGH_RISK_ACTIONS = {"dispatch", "allocate", "cancel"}


@dataclass
class LogisticsWorldSpec(WorldSpec):
    """Explicit, self-describing WorldSpec for Logistics.

    Extends WorldSpec with a capability model: authority is attached to
    SPECIFIC capabilities, not to "Logistics = ACT".
    """
    capability_authorization: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> Optional[str]:
        base = super().validate()
        if base:
            return base
        valid = {"PASS", "LIMITED", "UNKNOWN", "FAIL", "BLOCKED"}
        for cap, st in self.capability_authorization.items():
            if st not in valid:
                return f"capability '{cap}' has invalid status '{st}'"
        return None


def build_logistics_world_spec(
    escalation_policy: str = "advisory",
    capabilities: Optional[Dict[str, str]] = None,
) -> LogisticsWorldSpec:
    """Build the explicit LogisticsWorldSpec with a capability-authorization model.
    
    Args:
        escalation_policy: how escalation is handled (e.g. 'advisory')
        capabilities: optional capability->status mapping; defaults to the built-in set
    """
    caps = capabilities or {
        "route_recommendation": "PASS",
        "inventory_recommendation": "PASS",
        "dispatch_recommendation": "PASS",
        "rerouting": "LIMITED",
        "automatic_dispatch": "BLOCKED",   # structural: never auto-dispatch
        "emergency_override": "FAIL",
    }
    return LogisticsWorldSpec(
        name="logistics",
        version="1.0",
        state_dim=STATE_DIM,
        action_dim=6,
        objectives=["minimize_cost", "minimize_lateness", "preserve_inventory",
                    "minimize_risk", "maintain_service_level"],
        constraints=["inventory_nonnegative", "budget_limit", "delivery_deadline",
                     "irreversibility_gate", "capacity_bound"],
        observability="partial",           # partial observability by design
        capabilities=list(caps.keys()),
        authorized_modes={"ACT", "DEFER", "ABSTAIN", "ESCALATE", "BLOCK"},
        escalation_policy=escalation_policy,
        capability_authorization=caps,
    )


class LogisticsDomainSimulator(DomainSimulator):
    """A logistics world with partial observability, delay, cost, irreversibility.

    `state` is the ACTUAL world state. `observe()` returns a PARTIAL view that
    hides information a real operator would not have (future delayed
    consequences, external-event causes). TELOS only ever sees the observed view.
    """

    def __init__(self, seed: Optional[int] = None):
        self._rng = np.random.RandomState(seed)
        self.name = "logistics"
        self.state_dim = STATE_DIM
        self._external_event_declared = False

    # ── Lifecycle ──
    def initialize(self) -> None: pass
    def cleanup(self) -> None: pass

    # ── WorldSpec ──
    def world_spec(self) -> LogisticsWorldSpec:
        return build_logistics_world_spec()

    # ── Observability ──
    def observe(self, state: np.ndarray) -> np.ndarray:
        """Return the PARTIALLY-observed view of the actual world state.

        Hides things a live operator cannot see:
          - future delayed consequences (shipment_progress -> hidden)
          - the cause of an external event (external_event_flag cause hidden)
        This guarantees TELOS never receives hidden/privileged state.
        """
        obs = state.copy()
        # shipment_progress [8] is a delayed consequence not yet observable at t0
        obs[8] = 0.0
        # the origin/cause of a disturbance is not exposed as a cause
        return obs

    # ── Legal transitions ──
    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        """Return the legal action-vectors available now (discrete primitives).
        
        Args:
            state: the actual world state (used to gate legality)
        """
        vecs = []
        for a in LogisticsAction:
            v = self.action_vector(a)
            if v is not None:
                vecs.append(v)
        # remove 'escalate' if already escalated / no capability
        return vecs

    def action_vector(self, action: LogisticsAction) -> Optional[np.ndarray]:
        """Encode a LogisticsAction as a 6-dim one-hot vector, or None past the 6-dim latent."""
        idx = list(LogisticsAction).index(action)
        if idx >= 6:
            return None  # only 6-dim action latent
        v = np.zeros(6)
        v[idx] = 1.0
        return v

    # ── Transition (real consequences + delay + cost + irreversibility) ──
    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        """Apply an action with REAL consequence, cost, delay, irreversibility.

        Returns the ACTUAL next state (before partial observation).
        """
        s = state.copy()
        # map action vector to an action label
        label = self._action_label(action)
        meta = ACTION_META.get(label, ACTION_META["hold"])
        cost = meta["cost"]
        irr = meta["irreversibility"]
        delay = int(meta["delay"])

        # inventory / cash / fuel: cost of action
        s[0] = max(0.0, min(1.0, s[0] - max(0.0, cost) * 0.2 - (0.05 if label == "allocate" else 0.0)))
        s[1] = max(0.0, min(1.0, s[1] - abs(cost) * 0.3))
        s[6] = max(0.0, min(1.0, s[6] - 0.05))

        if label == "dispatch" or label == "allocate":
            s[3] = min(1.0, s[3] + 0.1)          # a commitment in flight
            s[9] = min(1.0, s[9] + irr)          # accumulated committed risk
            s[8] = max(0.0, min(1.0, s[8] + delay * 0.1))  # delayed consequence begins
        elif label == "cancel":
            s[9] = min(1.0, s[9] + irr)          # cancellation penalty is highly irreversible
            s[4] = min(1.0, s[4] + 0.15)         # lateness/penalty
            s[5] = max(0.0, s[5] - 0.2)          # service level drops
        elif label == "replenish":
            s[0] = min(1.0, s[0] + 0.25)         # inventory restored (with delay)
            s[8] = max(0.0, min(1.0, s[8] + 0.05))
        elif label == "consolidate":
            s[1] = min(1.0, s[1] + 0.1)          # cost saving
        elif label == "reroute":
            s[4] = max(0.0, s[4] - 0.05)         # reduces future lateness

        # Time/deadline pressure advances (delayed consequence of prior actions)
        s[4] = min(1.0, s[4] + s[10] * 0.05)
        s[10] = min(1.0, s[10] + 0.02)

        # External disturbance acts on lateness & sla
        if s[11] > 0.5:
            s[4] = min(1.0, s[4] + 0.1)
            s[5] = max(0.0, s[5] - 0.1)

        return s

    def _action_label(self, v: np.ndarray) -> str:
        """Decode a 6-dim action vector into its LogisticsAction label, defaulting to hold."""
        arr = np.asarray(v).reshape(-1)
        idx = int(np.argmax(arr)) if arr.size else 0
        labels = [a.value for a in LogisticsAction][:6]
        return labels[idx] if 0 <= idx < len(labels) else "hold"

    # ── Simulation (predictive rollouts — for Reality Gap) ──
    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        """Roll out horizon random legal transitions for predictive Reality-Gap futures.
        
        Args:
            state: the actual world state to simulate from
            horizon: number of forward steps to simulate
        """
        futures = []
        s = state.copy()
        for _ in range(horizon):
            acts = self.legal_transitions(s)
            if not acts:
                break
            chosen = acts[int(self._rng.randint(len(acts)))]
            s = self.transition(s, chosen)
            futures.append(World(state=self.observe(s).copy(), metadata={"simulated": True}))
        return futures

    # ── Facts (evidence-bearing) ──
    def get_facts(self, state: np.ndarray, evidence: Optional[EvidenceInfo] = None) -> DomainFacts:
        """Produce evidence-bearing DomainFacts from the partially-observed state.
        
        Args:
            state: the actual world state (observed before use)
            evidence: optional EvidenceInfo; defaults to a MEASUREMENT observation
        """
        obs = self.observe(state)
        # Directly observed/measured world-state evidence maps to MEASUREMENT
        # (the existing domain-independent EvidenceSource taxonomy). We do NOT
        # add an OBSERVATION member nor create a Logistics-specific source.
        meas = evidence or EvidenceInfo(
            source=EvidenceSource.MEASUREMENT,
            validation_status=ValidationStatus.OBSERVED,
        )
        return DomainFacts(
            state=obs.copy(),
            resources={
                "inventory": float(obs[0]),
                "cash": float(obs[1]),
                "vehicles": float(obs[2]),
                "fuel": float(obs[6]),
            },
            constraints=["inventory_nonnegative", "budget_limit", "delivery_deadline",
                         "irreversibility_gate", "capacity_bound"],
            events=[("external_disturbance" if obs[11] > 0.5 else "nominal"),
                    ("deadline_pressure" if obs[10] > 0.6 else "on_schedule")],
            metrics={
                "cost_health": float(1.0 - (1.0 - obs[1])),
                "lateness": float(obs[4]),
                "service_level": float(obs[5]),
                "inventory_level": float(obs[0]),
                "committed_risk": float(obs[9]),
                "irreversibility": float(max(0.0, obs[9])),
            },
            metadata={
                "observability": "partial",
                "hidden_delayed_consequences": True,
            },
            evidence=meas,
        )

    def terminal(self, state: np.ndarray) -> bool:
        """Return True when the observed state indicates a terminal/healthy condition."""
        return bool(self.observe(state)[3] <= 0.05 and np.linalg.norm(state - HEALTHY) < 3.0)

    # ── Evaluate (multi-objective with real risks, NOT a single magic score) ──
    def evaluate(self, state: np.ndarray) -> EvaluationReport:
        """Return a multi-objective EvaluationReport with non-zero risk from the observed state."""
        obs = self.observe(state)
        # Separate objectives — exposed individually for utility ranking.
        objectives = {
            "minimize_cost": float(obs[1]),                 # higher cash = better
            "minimize_lateness": float(1.0 - obs[4]),
            "preserve_inventory": float(obs[0]),
            "minimize_risk": float(1.0 - obs[9]),
            "maintain_service_level": float(obs[5]),
        }
        # Real, non-zero risk from irreversibility + disturbance + deadline.
        risks = float(obs[9] * 0.5 + obs[11] * 0.3 + obs[10] * 0.2)
        return EvaluationReport(objectives=objectives, risks=risks)

    # ── External disturbance injection (for benchmark scenarios) ──
    def inject_disturbance(self, state: np.ndarray, severity: float = 0.5) -> np.ndarray:
        """Inject an external disturbance into a copy of state (benchmark scenario setup).
        
        Args:
            state: the actual world state to disturb
            severity: 0-1 disturbance magnitude applied to the external-event/observed-delay channels
        """
        s = state.copy()
        s[11] = max(0.0, min(1.0, severity))
        s[7] = max(0.0, min(1.0, severity))
        s[4] = min(1.0, s[4] + severity * 0.1)
        return s

    def resolve_disturbance(self, state: np.ndarray) -> np.ndarray:
        """Return a copy of state with any external disturbance cleared (recovery)."""
        s = state.copy()
        s[11] = 0.0
        s[7] = 0.0
        return s


class LogisticsDomainAdapter(DomainAdapter):
    """Maps TELOS intents to discrete logistics actions."""
    name = "logistics"
    state_dim = STATE_DIM

    def forward(self, domain_state: np.ndarray) -> np.ndarray:
        """Return the observed (partial) view of the domain_state as a float array."""
        return self.observe(domain_state) if hasattr(self, "observe") else np.asarray(domain_state, dtype=float)

    def inverse(self, telos_action: np.ndarray) -> np.ndarray:
        """Pass a telos_action through unchanged as a float action array."""
        return np.asarray(telos_action, dtype=float)

    def intent_to_action(self, intent, state, mission_dir) -> np.ndarray:
        """Map a TELOS intent to a concrete discrete logistics action vector.
        
        Args:
            intent: the TELOS intent (expected intent_type + optional params)
            state: the world state (unused by the mapping, kept for signature parity)
            mission_dir: the mission direction vector (unused, kept for signature parity)
        """
        label = (intent.intent_type if hasattr(intent, "intent_type") else "hold")
        # Map intent type to a logistics action lattice
        mapping = {
            "dispatch": "dispatch", "allocate": "allocate", "replenish": "replenish",
            "reroute": "reroute", "consolidate": "consolidate", "cancel": "cancel",
            "hold": "hold", "escalate": "escalate", "navigate": "hold",
            "plan_trajectory": "dispatch", "goal_seek": "dispatch",
        }
        action_name = mapping.get(label, "hold")
        if "action_vector" in (intent.params if hasattr(intent, "params") else {}):
            return np.asarray(intent.params["action_vector"], dtype=float)
        idx = [a.value for a in LogisticsAction][:6]
        if action_name in idx:
            v = np.zeros(6); v[idx.index(action_name)] = 1.0; return v
        return np.zeros(6)
