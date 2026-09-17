"""
External Axiom Falsifier — an independent adversary for the AxiomProver.

WHY THIS EXISTS (the self-reference gap)
----------------------------------------
The AxiomProver checks predicates that the same codebase defines. A green
prover therefore only proves *internal consistency*, not that an axiom can
ever be violated. This module closes that gap from the outside: for every
axiom it constructs a *sabotaged* context that the axiom's own semantics say
must FAIL, runs the real prover on it, and asserts the prover actually
reports failure.

An axiom that cannot be made to fail is not verified — it is unfalsifiable.
The falsifier reports those honestly rather than letting them pass silently.

This is mutation testing applied to the constitution: we do not trust the
prover's predicate; we attack its inputs and require it to notice.

Usage:
    falsifier = AxiomFalsifier()
    report = falsifier.run()
    assert report["unfalsifiable"] == [], report["unfalsifiable"]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

from telos.core.verifier.axiom_prover import AxiomProver


class _Activation(SimpleNamespace):
    """Minimal StreamActivation stand-in (only `activated` is read)."""


@dataclass
class _Setup:
    """A complete, healthy prover input that satisfies all 42 axioms.

    Attributes:
        trace: the DecisionTrace stand-in.
        ctx: the PhaseContext stand-in.
        kwargs: extra prover keyword arguments.
        infra: the infra_manager stand-in.
        sl: the skill_library stand-in.
    """

    trace: Any
    ctx: Any
    kwargs: Dict[str, Any]
    infra: Any
    sl: Any


def healthy_setup() -> _Setup:
    """Build a prover input on which all 42 axioms pass.

    Returns:
        A `_Setup` whose every channel is populated, so any single sabotage
        that flips one axiom can only be attributed to that sabotage.
    """
    trace = SimpleNamespace(
        decision_integrity=1.0,
        mission_drift=0.0,
        council_validated=True,
        spent_ctx_id="ctx-a",
        produced_ctx_id="ctx-b",
        causal_graph={},
        strategic_options=[object()],
        local_optima_escape=True,
        attention_metrics={},
        j_term_breakdown={"alignment_cost": 0.0, "opportunity_cost": 0.0},
        selected_intent=object(),
        error_attribution={},
        axiom_results=None,
    )
    ctx = SimpleNamespace(
        governance_blocked=False,
        resource_budgets={"energy": {"consumed_ms": 1.0, "total_ms": 10.0}},
        meta_cognition={
            "recovery_mode": False,
            "exploration_mode": True,
            "mode": "standard",
            "current_state": "stable",
        },
        reflection={},
        error_attribution={},
        curiosity_state={},
        identity_state={},
        stream_activations=[_Activation(activated=True), _Activation(activated=True)],
    )
    kwargs: Dict[str, Any] = {
        "model_competition": SimpleNamespace(
            dominant_model="m", compute_entropy=lambda *a, **k: 1.0),
        "relational_context": SimpleNamespace(relational_coherence=1.0),
        "cooperative_intelligence": SimpleNamespace(cooperative=True),
        "system_self": object(),
        "theory_builder": object(),
        "axiom_evolution": object(),
        "resource_gradient": object(),
        "cognitive_momentum": object(),
        "interpretation_engine": object(),
        "identity_compression": object(),
        "explanation_compression": object(),
        "curiosity_drive": object(),
        "unknown_unknown_detector": object(),
        "pipeline": None,
    }
    infra = SimpleNamespace(
        failures=[],
        calibrator=object(),
        policy=SimpleNamespace(current=SimpleNamespace(
            risk_tolerance=0.3, exploration_budget=0.3)),
    )
    sl = SimpleNamespace(find_relevant_skills=lambda *a, **k: [])
    return _Setup(trace=trace, ctx=ctx, kwargs=kwargs, infra=infra, sl=sl)


# ── Sabotage specs: axiom_id -> attacker(setup) ─────────────────────────────
# Each attacker degrades exactly the dependency the axiom claims to govern.
# If the prover does not report the target axiom failed, the axiom is
# unfalsifiable (a real finding, not a pass).

def _sabotages() -> Dict[str, Callable[[_Setup], None]]:
    """Build the axiom_id -> sabotage function table.

    Returns:
        Mapping from axiom id to a callable that corrupts the specific
        channel that axiom is supposed to protect.
    """
    def null_trace(s: _Setup) -> None:
        s.trace = None

    specs: Dict[str, Callable[[_Setup], None]] = {}

    # Layer 1
    specs["1.1"] = null_trace
    specs["1.2"] = lambda s: setattr(s.trace, "decision_integrity", -1.0)
    specs["1.3"] = lambda s: setattr(s.ctx, "governance_blocked", None)
    specs["1.4"] = lambda s: setattr(
        s.ctx, "resource_budgets", {"energy": {"consumed_ms": 999.0, "total_ms": 10.0}})

    # Layer 2
    specs["2.1"] = lambda s: setattr(s.trace, "council_validated", None)
    specs["2.2"] = lambda s: setattr(s.ctx, "meta_cognition", None)
    specs["2.3"] = lambda s: setattr(s.infra, "failures", None)
    specs["2.4"] = lambda s: (setattr(s.trace, "spent_ctx_id", None),
                              setattr(s.trace, "produced_ctx_id", None))
    specs["2.5"] = lambda s: delattr(s.trace, "causal_graph")
    specs["2.6"] = lambda s: setattr(s.ctx, "reflection", None)
    specs["2.7"] = lambda s: (setattr(s.ctx, "error_attribution", None),
                              setattr(s.trace, "error_attribution", None))

    # Layer 3
    specs["3.1"] = lambda s: s.ctx.meta_cognition.pop("recovery_mode", None)
    specs["3.2"] = lambda s: setattr(s.ctx, "resource_budgets", None)
    specs["3.3"] = lambda s: (setattr(s.sl, "find_relevant_skills", None),)
    specs["3.4"] = lambda s: s.ctx.meta_cognition.pop("exploration_mode", None)
    specs["3.5"] = lambda s: setattr(s.infra, "calibrator", None)
    specs["3.6"] = lambda s: setattr(s.ctx, "curiosity_state", None)

    # Layer 4
    specs["4.1"] = lambda s: setattr(s.ctx, "identity_state", None)
    specs["4.2"] = lambda s: setattr(s.infra, "policy", None)
    specs["4.3"] = lambda s: setattr(s.trace, "strategic_options", [])
    specs["4.4"] = lambda s: setattr(s.trace, "council_validated", False)
    specs["4.5"] = lambda s: setattr(s.trace, "local_optima_escape", None)
    specs["4.6"] = lambda s: setattr(
        s.ctx, "stream_activations", [_Activation(activated=True)])
    specs["4.7"] = lambda s: setattr(s.trace, "attention_metrics", None)
    specs["4.8"] = lambda s: s.kwargs.__setitem__("model_competition", None)
    specs["4.9"] = lambda s: s.kwargs.__setitem__("relational_context", None)
    specs["4.10"] = lambda s: s.kwargs.__setitem__("system_self", None)
    specs["4.11"] = lambda s: s.kwargs.__setitem__(
        "cooperative_intelligence", SimpleNamespace(cooperative=False))

    # Layer 5
    specs["5.1"] = lambda s: (setattr(s.trace, "j_term_breakdown", None),
                              setattr(s.trace, "selected_intent", None))
    specs["5.2"] = lambda s: s.kwargs.__setitem__("axiom_evolution", None)
    specs["5.3"] = lambda s: setattr(s.trace, "j_term_breakdown", {})

    # Layer 6
    specs["6.1"] = lambda s: s.kwargs.__setitem__("resource_gradient", None)
    specs["6.2"] = lambda s: s.kwargs.__setitem__("cognitive_momentum", None)
    specs["6.3"] = lambda s: s.kwargs.__setitem__("interpretation_engine", None)
    specs["6.4"] = lambda s: s.kwargs.__setitem__("identity_compression", None)
    specs["6.5"] = lambda s: s.kwargs.__setitem__("theory_builder", None)
    specs["6.6"] = lambda s: s.kwargs.__setitem__("model_competition", None)
    specs["6.7"] = lambda s: s.kwargs.__setitem__("explanation_compression", None)
    specs["6.8"] = lambda s: s.kwargs.__setitem__("system_self", None)
    specs["6.9"] = lambda s: s.kwargs.__setitem__("curiosity_drive", None)
    specs["6.10"] = lambda s: s.kwargs.__setitem__("unknown_unknown_detector", None)
    specs["6.11"] = lambda s: setattr(s.trace, "j_term_breakdown", {})

    return specs


class AxiomFalsifier:
    """Attacks the AxiomProver's inputs and requires it to report failures."""

    def __init__(self, sabotage: Optional[Dict[str, Callable[[_Setup], None]]] = None):
        """Initialize the falsifier.

        Args:
            sabotage: optional override table (axiom_id -> attacker). Defaults
                to the canonical `_sabotages()` table.
        """
        self._sabotage = sabotage if sabotage is not None else _sabotages()

    @staticmethod
    def _prover_for(setup: _Setup) -> AxiomProver:
        """Build a prover wired to the setup's infra/skill channels.

        Args:
            setup: the healthy or sabotaged setup.

        Returns:
            An AxiomProver instance.
        """
        return AxiomProver(infra_manager=setup.infra, skill_library=setup.sl)

    def _verify(self, setup: _Setup) -> Dict[str, Dict[str, Any]]:
        """Run the real prover against a setup.

        Args:
            setup: the prover input to evaluate.

        Returns:
            The prover's axiom_id -> {passed, reason} mapping.
        """
        return self._prover_for(setup).verify(
            setup.trace, setup.ctx, **setup.kwargs)

    def run(self) -> Dict[str, Any]:
        """Execute the full adversarial suite.

        Returns:
            A report with keys:
                healthy_passed: bool (all axioms pass on the healthy setup)
                healthy_failed: list of axiom ids failing the healthy setup
                falsifiable: sorted list of axioms that CAN be made to fail
                unfalsifiable: sorted list of axioms that could NOT be failed
                results: per-axiom detail dict
        """
        results: Dict[str, Any] = {}
        healthy = healthy_setup()
        baseline = self._verify(healthy)
        healthy_failed = sorted(aid for aid, r in baseline.items() if not r["passed"])

        falsifiable: List[str] = []
        unfalsifiable: List[str] = []

        for axiom_id, attacker in sorted(self._sabotage.items()):
            setup = healthy_setup()
            try:
                attacker(setup)
                verdict = self._verify(setup)
                target_failed = not verdict.get(axiom_id, {}).get("passed", True)
            except Exception as exc:  # a sabotage that crashes is a harness bug
                target_failed = False
                verdict = {axiom_id: {"passed": None, "reason": f"sabotage error: {exc}"}}
            caught = bool(target_failed)
            (falsifiable if caught else unfalsifiable).append(axiom_id)
            results[axiom_id] = {
                "falsifiable": caught,
                "reason": verdict.get(axiom_id, {}).get("reason", ""),
            }

        # Axioms absent from the sabotage table are unfalsifiable by definition.
        for axiom_id in baseline:
            if axiom_id not in self._sabotage and axiom_id not in results:
                unfalsifiable.append(axiom_id)
                results[axiom_id] = {
                    "falsifiable": False,
                    "reason": "no sabotage defined — axiom cannot be externally falsified",
                }

        return {
            "healthy_passed": not healthy_failed,
            "healthy_failed": healthy_failed,
            "falsifiable": sorted(falsifiable),
            "unfalsifiable": sorted(set(unfalsifiable)),
            "results": results,
        }


__all__ = ["AxiomFalsifier", "healthy_setup"]
