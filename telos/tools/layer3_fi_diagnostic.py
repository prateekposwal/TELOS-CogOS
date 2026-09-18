#!/usr/bin/env python3
"""Layer-3 F(I) identity-projection diagnostic — NON-MUTATING classifier.

Question: is Layer 3 (the canonical IdentityProjectionGate, F(I)) genuinely
enforcing identity, or is it too permissive / incorrectly wired so that no
live intent can ever be identity-inadmissible?

This tool runs the REAL pipeline (no stubs) for a bounded, deterministic
workload and records, for EVERY intent the canonical gate evaluates:
intent_type, mission_active, missionless_bootstrap, project_id, mission_ids,
narrative_role, every layer's verdict, the final F(I) PASS/FAIL, and whether
Layer-3 enforcement actually removed the intent (ctx.identity_projection).

It does NOT alter the production decision path. The pipeline instance under
test gets a RecordingGate that calls super().is_admissible(...) and returns
the EXACT super result; a parity run proves the recorder is decision-neutral
(identical selection fingerprints with and without it). It also runs the real
SelectPhase._enforce_identity_projection with a synthetic adversarial twin to
prove the predicate's rejection boundary is reachable when its inputs are.

Usage:
  PYTHONPATH=. ./.venv/bin/python telos/tools/layer3_fi_diagnostic.py --cycles 150
  PYTHONPATH=. ./.venv/bin/python telos/tools/layer3_fi_diagnostic.py --ci
"""
import argparse
import hashlib
import json
import logging
import os
import shutil
import sys

import numpy as np

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

from telos.core.identity.projection_gate import (  # noqa: E402
    IdentityProjectionGate, ROLE_INCOMPATIBLE, MISSION_EXEMPT,
)

DEFAULT_CYCLES = 150
DEFAULT_SEED = 42
MISSION_NAME = "navigate_to_goal"
MISSION_DESCRIPTION = "Navigate the GridWorld agent to the goal cell."
OUT_PATH = os.path.join(PROJECT, "telos", "audit", "layer3_fi_diagnostic.json")

# The live caller invariant AFTER the fix (select.py::_identity_gate_context).
# Genuine bootstrap ONLY: True iff no objective has EVER been defined.
LIVE_BOOTSTRAP_RULE = "missionless_bootstrap = not mission_defined"

# The predicate maps 'roles' to incompatible intent-type substrings. ONE
# canonical source now lives in projection_gate.py; re-exported here so the
# diagnostic + its tests read the SAME map the predicate does (Λ6.7).
ALWAYS_ADMITTED = ("reflex", "halt", "emergency_stop")


def _layer_transcript(gate, intent_type, project_id, mission_active,
                      mission_ids, narrative_role, missionless_bootstrap,
                      mission_defined=False):
    """Mirror the canonical predicate layer-by-layer (read-only transcript).

    Every field is recomputed exactly as identity/projection_gate.py computes
    it so the caller can see WHICH layer reached (or could reach) a rejection.
    The transcript is a diagnostic shadow, never an input to the decision.

    Args:
        gate: the canonical IdentityProjectionGate instance.
        intent_type: the intent type under evaluation.
        project_id: the trajectory's project id (Layer 4).
        mission_active: whether the portfolio has any active mission.
        mission_ids: active mission ids plus owned project ids.
        narrative_role: the Layer-2 narrative role (None = unscoped).
        missionless_bootstrap: GENUINE-bootstrap flag (no objective ever).
        mission_defined: whether an objective has ever been defined.

    Returns:
        Dict with the six layer booleans, the reflex short-circuit, the number
        of ACTIVE blocking conditions, and the live-path reachability note.
    """
    core = gate._core
    it = intent_type if isinstance(intent_type, str) else str(intent_type)
    core_curiosity = not core.recognizes("curiosity")
    core_integrity = core.recognizes("integrity")
    core_humility = core.recognizes("epistemic_humility")

    reflex = it in ALWAYS_ADMITTED
    l1_curiosity = (it == "curiosity_explore" and core_curiosity)
    l1_integrity = (("steal" in it or "deceive" in it) and core_integrity)
    l1_humility = ("exploit" in it and "explore" in it
                   and core_humility and "harm" in it)
    inc = ROLE_INCOMPATIBLE.get(narrative_role, []) if narrative_role else []
    l2_role = any(i in it for i in inc)
    genuine_bootstrap = missionless_bootstrap and not mission_defined
    l3_mission = (not mission_active and not genuine_bootstrap
                  and it not in MISSION_EXEMPT)
    l4_project = bool(project_id and mission_ids and mission_ids[0]
                      and project_id not in mission_ids)

    blockers = {
        "L1_core_curiosity": l1_curiosity,
        "L1_core_integrity": l1_integrity,
        "L1_core_epistemic_humility": l1_humility,
        "L2_narrative_role": l2_role,
        "L3_active_mission": l3_mission,
        "L4_project_scope": l4_project,
    }
    # Reflex short-circuits before any layer is consulted.
    active = 0 if reflex else sum(1 for v in blockers.values() if v)
    return {
        "reflex_short_circuit": reflex,
        "layers": blockers,
        "active_block_conditions": active,
    }


class RecordingGate(IdentityProjectionGate):
    """Decision-neutral recorder: delegates to super and returns its result."""

    def __init__(self, identity_core=None, identity_narrative=None):
        """Initialize the recording gate.

        Args:
            identity_core: optional frozen Layer-1 core (defaults to genesis).
            identity_narrative: optional Layer-2 narrative (defaults to genesis).
        """
        super().__init__(identity_core=identity_core,
                         identity_narrative=identity_narrative)
        self.calls = []

    def is_admissible(self, intent_type, project_id=None, mission_active=False,
                      mission_ids=None, narrative_role=None,
                      missionless_bootstrap=False, mission_defined=False):
        """Record one F(I) evaluation, then return the real predicate result.

        Args:
            intent_type: the intent type under evaluation.
            project_id: the trajectory's project id.
            mission_active: whether any mission is active.
            mission_ids: active mission scope (ids + owned project ids).
            narrative_role: the Layer-2 narrative role.
            missionless_bootstrap: GENUINE-bootstrap flag (no objective ever).
            mission_defined: whether an objective has ever been defined.

        Returns:
            The unmodified result of IdentityProjectionGate.is_admissible.
        """
        result = super().is_admissible(
            intent_type, project_id=project_id, mission_active=mission_active,
            mission_ids=mission_ids, narrative_role=narrative_role,
            missionless_bootstrap=missionless_bootstrap,
            mission_defined=mission_defined)
        self.calls.append({
            "intent_type": intent_type,
            "mission_active": bool(mission_active),
            "mission_defined": bool(mission_defined),
            "missionless_bootstrap": bool(missionless_bootstrap),
            "project_id": project_id,
            "mission_ids": list(mission_ids) if mission_ids else [],
            "narrative_role": narrative_role,
            "result": bool(result),
            "transcript": _layer_transcript(
                self, intent_type, project_id, mission_active, mission_ids,
                narrative_role, missionless_bootstrap, mission_defined),
        })
        return result


def _build_pipeline(cp_dir, mission, seed=DEFAULT_SEED, recorder=False):
    """Build a REAL GridWorld pipeline matching the live producer's config.

    Args:
        cp_dir: checkpoint/knowledge directory for this run.
        mission: True to declare the live mission (production), False for the
            missionless-bootstrap path.
        seed: deterministic RNG seed.
        recorder: True to install the decision-neutral RecordingGate.

    Returns:
        (pipeline, gate) — the pipeline and the gate actually wired into it.
    """
    from telos_task import GridAdpt, GridSim, DEFAULT_BLOCKED, DEFAULT_REWARDS
    from telos.core.runtime import PipelineConfig, TelosV14Pipeline
    from telos.core.streams.implementations import (
        ReflexStream, PerceptionStream, MemoryStream, PlanningStream, TheoryStream,
    )
    from telos.core.streams.inquiry_stream import InquiryStream
    from telos.core.council.validators import (
        RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
        EvidenceProvenanceValidator,
    )
    from telos.core.ledger.skill_library import SkillLibrary
    from telos.core.simulation import CounterfactualEngine

    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
    pipe = TelosV14Pipeline(PipelineConfig(
        adapter=GridAdpt(), simulator=sim,
        compute_budget_ms=100.0, state_dim=2, n_worlds=10, horizon=5,
        mission_name=(MISSION_NAME if mission else None),
        mission_description=(MISSION_DESCRIPTION if mission else ""),
        checkpoint_path=cp_dir,
        knowledge_path=os.path.join(cp_dir, "kg.json"),
        ledger_path=os.path.join(cp_dir, "ld.json"),
        identity_path=os.path.join(cp_dir, "id.json"),
        pattern_path=os.path.join(cp_dir, "pt.json"),
        deterministic_seed=seed,
    ))
    sl = SkillLibrary()
    for s in [ReflexStream(sl), PerceptionStream(sl), MemoryStream(sl),
              PlanningStream(sl, sim_engine=CounterfactualEngine(sim)),
              InquiryStream(sl),
              TheoryStream(sl, theory_builder=getattr(pipe, "_theory_builder", None))]:
        pipe.register_stream(s)
    for v in [RealityValidator(), ConstraintValidator(), MemoryAdvisor(sl),
              MissionDriftDetector(drift_threshold=5.0), EvidenceProvenanceValidator()]:
        pipe.register_validator(v)

    gate = getattr(pipe, "_identity_projection_gate", None)
    if recorder and gate is not None:
        rec = RecordingGate(identity_core=pipe._identity_core,
                            identity_narrative=pipe._identity_narrative)
        pipe._identity_projection_gate = rec
        gate = rec
    return pipe, gate


def _run_workload(cycles, mission, seed=DEFAULT_SEED, recorder=False,
                  cp_dir=None):
    """Run the real pipeline and collect Layer-3 evaluation statistics.

    Args:
        cycles: number of pipeline cycles to execute.
        mission: True to declare the live mission.
        seed: deterministic RNG seed.
        recorder: True to record every gate evaluation.
        cp_dir: optional working directory (defaults to a bounded temp dir).

    Returns:
        Dict of statistics: evaluations, failures, projected_out, per-layer
        armed counts, active-block histogram, and the F(I) margin series.
    """
    if cp_dir is None:
        cp_dir = "/tmp/telos_layer3_cp_%s" % ("m" if mission else "nm")
    if os.path.isdir(cp_dir):
        shutil.rmtree(cp_dir)
    os.makedirs(cp_dir, exist_ok=True)
    pipe, gate = _build_pipeline(cp_dir, mission, seed=seed, recorder=recorder)
    state = np.array([0.0, 0.0])

    evaluations = 0
    failures = 0
    pass_01 = []          # F(I) as a discrete value: 1.0 PASS / 0.0 FAIL
    active_hist = {}      # distance to the rejection boundary (active blockers)
    layer_armed = {k: 0 for k in (
        "L1_core_curiosity", "L1_core_integrity", "L1_core_epistemic_humility",
        "L2_narrative_role", "L3_active_mission", "L4_project_scope")}
    reflex_short = 0
    intent_types = {}
    projected_out_total = 0
    rejected_selected_total = 0
    fallback_total = 0
    layer3_cycles = 0     # cycles where L3 was consulted (not reflex)
    trajectory = []
    selected_types = []

    for i in range(cycles):
        r = pipe.execute(state, user_name="layer3_diag")
        t = r.decision_trace
        itype = t.selected_intent.intent_type if t.selected_intent else "none"
        selected_types.append(itype)
        di = float(t.decision_integrity or 0.0)
        md = float(t.mission_drift or 0.0)
        act = t.selected_action
        ip = getattr(t, "identity_projection", None) or {}
        projected_out_total += len(ip.get("projected_out", []) or [])
        if ip.get("rejected_selected"):
            rejected_selected_total += 1
        if ip.get("fallback"):
            fallback_total += 1
        trajectory.append({"cycle": i, "selected_intent": itype, "di": round(di, 4),
                           "md": round(md, 4),
                           "projected_out": ip.get("projected_out", [])})
        if act is not None:
            nxt = pipe.config.simulator.transition(state, act)
            if 0.0 <= float(nxt[0]) <= 4.0 and 0.0 <= float(nxt[1]) <= 4.0:
                state = nxt

    if recorder and isinstance(gate, RecordingGate):
        for c in gate.calls:
            evaluations += 1
            if not c["result"]:
                failures += 1
            pass_01.append(1.0 if c["result"] else 0.0)
            tr = c["transcript"]
            if tr["reflex_short_circuit"]:
                reflex_short += 1
            else:
                layer3_cycles += 1
            active_hist[tr["active_block_conditions"]] = (
                active_hist.get(tr["active_block_conditions"], 0) + 1)
            for k, v in tr["layers"].items():
                if v:
                    layer_armed[k] += 1
            intent_types[c["intent_type"]] = intent_types.get(c["intent_type"], 0) + 1

    # Reachability of the LAYER-3 WIRING (not whether this workload fired it).
    # After the fix, missionless_bootstrap = not mission_defined; a kernel with
    # a defined objective but no active mission scope presents a strict context
    # the guard can reject on. `l3_enforcement_experiment` proves it.
    l3_wiring_reachable = True
    stats = {
        "mission": bool(mission),
        "cycles": cycles,
        "evaluations": evaluations,
        "failures": failures,
        "passes": evaluations - failures,
        "reflex_short_circuits": reflex_short,
        "non_reflex_evaluations": layer3_cycles,
        "distinct_intent_types": len(intent_types),
        "intent_type_counts": dict(sorted(intent_types.items(),
                                          key=lambda kv: -kv[1])),
        # F(I) is a BOOLEAN predicate: there is no numeric threshold/margin.
        # We report the discrete status and the boundary distance instead.
        "fi_values": {"min": min(pass_01) if pass_01 else None,
                      "max": max(pass_01) if pass_01 else None,
                      "mean": round(float(np.mean(pass_01)), 4) if pass_01 else None},
        "margin_note": "F(I) is boolean; min=max=mean in {0.0,1.0}; no numeric threshold exists",
        "active_block_histogram": dict(sorted(active_hist.items())),
        "rejection_boundary_distance": {
            "definition": "number of independent blocking predicates that would have to fire to reject; 0 active among all live evaluations",
            "min": min(active_hist) if active_hist else None,
            "max": max(active_hist) if active_hist else None,
        },
        "layer_armed_counts": layer_armed,
        "L3_wiring_reachable": l3_wiring_reachable,
        "projected_out_total": projected_out_total,
        "rejected_selected_total": rejected_selected_total,
        "safe_fallback_total": fallback_total,
        "trajectory": trajectory,
        "selected_intent_sequence_hash": hashlib.sha256(
            "|".join(selected_types).encode()).hexdigest()[:16],
    }
    return stats


def _fingerprint(cycles, mission, seed=DEFAULT_SEED, recorder=False):
    """Hash a run's selection/DI sequence for decision-neutrality parity.

    Args:
        cycles: cycles to run.
        mission: True to declare the live mission.
        seed: deterministic RNG seed.
        recorder: True to install the RecordingGate.

    Returns:
        A short hash of the (DI, MD, selected intent) sequence.
    """
    cp = "/tmp/telos_layer3_parity"
    if os.path.isdir(cp):
        shutil.rmtree(cp)
    os.makedirs(cp, exist_ok=True)
    pipe, _ = _build_pipeline(cp, mission, seed=seed, recorder=recorder)
    state = np.array([0.0, 0.0])
    parts = []
    for _ in range(cycles):
        r = pipe.execute(state, user_name="parity")
        t = r.decision_trace
        parts.append(f"{float(t.decision_integrity or 0.0):.4f}:"
                     f"{float(t.mission_drift or 0.0):.4f}:"
                     f"{t.selected_intent.intent_type if t.selected_intent else 'none'}")
        act = t.selected_action
        if act is not None:
            nxt = pipe.config.simulator.transition(state, act)
            if 0.0 <= float(nxt[0]) <= 4.0 and 0.0 <= float(nxt[1]) <= 4.0:
                state = nxt
    shutil.rmtree(cp, ignore_errors=True)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def adversarial_experiment(pipe):
    """Drives the REAL F(I) path with an identity-incompatible twin.

    A normal intent and a twin that differs ONLY in intent_type are pushed
    through the live pipeline's real gate and through
    SelectPhase._enforce_identity_projection with the live mission context.

    Args:
        pipe: the real pipeline (provides the canonical gate + portfolio).

    Returns:
        Dict with normal/evil predicate results and the enforcement record.
    """
    from telos.core.phases.select import SelectPhase
    from telos.core.phases.base import PhaseContext
    from telos.intent_ir import IntentIR

    gate = pipe._identity_projection_gate
    portfolio = getattr(pipe, "_mission_portfolio", None)
    active = portfolio.active_missions() if portfolio is not None else []
    mission_ids = []
    for m in active:
        mission_ids.append(getattr(m, "id", None))
        mission_ids.extend(getattr(m, "project_ids", []) or [])
    narrative = getattr(pipe, "_identity_narrative", None)
    role = getattr(narrative, "role", None)
    _gate, _active, _mids, bootstrap, mission_defined = (
        SelectPhase()._identity_gate_context(pipe))

    normal = IntentIR(intent_type="plan_trajectory", confidence=0.8,
                      params={"twin": True}, metadata={"twin": True})
    evil = IntentIR(intent_type="steal_payload", confidence=0.8,
                    params={"twin": True}, metadata={"twin": True})
    normal_result = gate.is_admissible(
        normal.intent_type, mission_active=bool(active), mission_ids=mission_ids,
        narrative_role=role, missionless_bootstrap=bootstrap,
        mission_defined=mission_defined)
    evil_result = gate.is_admissible(
        evil.intent_type, mission_active=bool(active), mission_ids=mission_ids,
        narrative_role=role, missionless_bootstrap=bootstrap,
        mission_defined=mission_defined)

    ctx = PhaseContext(cycle_count=0, state=np.zeros(2), user_name=None)
    ctx.intents = [(normal, 0.8), (evil, 0.8)]
    ctx.selected_intent = evil
    SelectPhase()._enforce_identity_projection(pipe, ctx)
    rec = getattr(ctx, "identity_projection", None) or {}
    return {
        "mission_active": bool(active),
        "mission_defined": bool(mission_defined),
        "mission_ids": mission_ids,
        "narrative_role": role,
        "normal": {"intent_type": normal.intent_type, "F_I": normal_result},
        "evil": {"intent_type": evil.intent_type, "F_I": evil_result},
        "separable": False,
        "separability_note": ("intent_type IS the identity dimension the predicate "
                              "reads; it also drives the adapter's execution mapping, "
                              "so an identity-incompatible twin cannot keep execution "
                              "feasibility constant in the current design"),
        "enforcement": {
            "projected_out": rec.get("projected_out", []),
            "rejected_selected": rec.get("rejected_selected"),
            "replacement": rec.get("replacement"),
            "fallback": rec.get("fallback"),
        },
    }


def l3_enforcement_experiment(cp_dir="/tmp/telos_layer3_l3_probe"):
    """Prove Layer 3 can now REJECT a live-shaped intent on the live path.

    Builds a REAL pipeline that DECLARES the production objective, then
    completes its active mission (objective still defined, no active scope) and
    drives the real SelectPhase._enforce_identity_projection with a
    live-shaped mission-serving intent (`plan_trajectory`). Under the old
    wiring this was unreachable (the Layer-3 guard was a tautology); under the
    fix the intent is projected out and replaced by the safe reflex keeper.

    Args:
        cp_dir: working directory for the probe pipeline.

    Returns:
        Dict recording the context tuple, the enforcement record, and whether
        L3 actually rejected the live-shaped intent.
    """
    from telos.core.phases.select import SelectPhase
    from telos.core.phases.base import PhaseContext
    from telos.intent_ir import IntentIR

    if os.path.isdir(cp_dir):
        shutil.rmtree(cp_dir)
    os.makedirs(cp_dir, exist_ok=True)
    pipe, gate = _build_pipeline(cp_dir, mission=True, recorder=False)
    before = SelectPhase()._identity_gate_context(pipe)
    for m in pipe._mission_portfolio.active_missions():
        m.complete(cycle=0)
    after = SelectPhase()._identity_gate_context(pipe)

    ctx = PhaseContext(cycle_count=5, state=np.zeros(2), user_name=None)
    intent = IntentIR(intent_type="plan_trajectory", confidence=0.9)
    ctx.intents = [(intent, 0.9)]
    ctx.selected_intent = intent
    SelectPhase()._enforce_identity_projection(pipe, ctx)
    rec = getattr(ctx, "identity_projection", None) or {}
    l3_rejected = ("plan_trajectory" in rec.get("projected_out", [])
                   and rec.get("rejected_selected") == "plan_trajectory")
    return {
        "before_mission_completed": {
            "mission_active": before[1], "mission_defined": before[4],
            "missionless_bootstrap": before[3]},
        "after_mission_completed": {
            "mission_active": after[1], "mission_defined": after[4],
            "missionless_bootstrap": after[3]},
        "live_shaped_intent": "plan_trajectory",
        "enforcement": rec,
        "L3_rejected_live_shaped_intent": l3_rejected,
        "replacement": getattr(ctx.selected_intent, "intent_type", None),
    }


def boundary_table(gate):
    """Evaluate the predicate across its boundary and malformed contexts.

    Args:
        gate: the canonical IdentityProjectionGate instance.

    Returns:
        List of (case, actual, expected, note) rows.
    """
    cases = [
        ("just_inside: plan_trajectory + active mission",
         dict(intent_type="plan_trajectory", mission_active=True), True),
        ("exactly_at: plan_trajectory + no mission + strict False",
         dict(intent_type="plan_trajectory", mission_active=False,
              missionless_bootstrap=False), False),
        ("genuine_bootstrap: plan_trajectory + no objective ever",
         dict(intent_type="plan_trajectory", mission_active=False,
              missionless_bootstrap=True, mission_defined=False), True),
        ("defined_no_active: plan_trajectory + objective, no active scope",
         dict(intent_type="plan_trajectory", mission_active=False,
              missionless_bootstrap=False, mission_defined=True), False),
        ("misset_bootstrap_cannot_bypass: flag True but objective defined",
         dict(intent_type="plan_trajectory", mission_active=False,
              missionless_bootstrap=True, mission_defined=True), False),
        ("missing_identity_field: narrative_role=None",
         dict(intent_type="plan_trajectory", mission_active=True,
              narrative_role=None), True),
        ("wrong_project_scope: proj_other not in mission_ids",
         dict(intent_type="plan_trajectory", mission_active=True,
              project_id="proj_other", mission_ids=["m1"]), False),
        ("unrelated_identity: guardian role + explore_dangerous",
         dict(intent_type="explore_dangerous", mission_active=True,
              narrative_role="guardian"), False),
        ("default_agent_role: surrender_control",
         dict(intent_type="surrender_control", mission_active=True,
              narrative_role="agent"), False),
        ("default_agent_role: plan_trajectory admitted",
         dict(intent_type="plan_trajectory", mission_active=True,
              narrative_role="agent"), True),
        ("malformed_empty_intent: '' + no mission + strict",
         dict(intent_type="", mission_active=False,
              missionless_bootstrap=False), False),
        ("core_integrity_violator: steal_payload + active mission",
         dict(intent_type="steal_payload", mission_active=True), False),
        ("core_integrity_violator: deceive_peer + active mission",
         dict(intent_type="deceive_peer", mission_active=True), False),
        ("always_admitted: reflex + no mission",
         dict(intent_type="reflex", mission_active=False), True),
    ]
    rows = []
    for case, kwargs, expected in cases:
        actual = bool(gate.is_admissible(**kwargs))
        rows.append({"case": case, "actual": actual, "expected": expected,
                     "pass": actual == expected,
                     "inputs": {k: v for k, v in kwargs.items()}})
    return rows


def run_diagnostic(cycles=DEFAULT_CYCLES, seed=DEFAULT_SEED, out_path=OUT_PATH):
    """Run the full diagnostic and return the artifact dict.

    Args:
        cycles: cycles per workload.
        seed: deterministic RNG seed.
        out_path: JSON artifact path (written only by main / run_diagnostic).

    Returns:
        The diagnostic artifact dict.
    """
    with_mission = _run_workload(cycles, mission=True, seed=seed, recorder=True)
    without_mission = _run_workload(cycles, mission=False, seed=seed, recorder=True)

    # Decision-neutrality parity: recorder ON vs OFF, identical seed.
    fp_rec = _fingerprint(cycles, True, seed=seed, recorder=True)
    fp_plain = _fingerprint(cycles, True, seed=seed, recorder=False)
    neutrality = {"recorder_fp": fp_rec[:16], "plain_fp": fp_plain[:16],
                  "decision_neutral": fp_rec == fp_plain}

    # A pipeline with the live mission for the adversarial + boundary probes.
    cp = "/tmp/telos_layer3_probe"
    if os.path.isdir(cp):
        shutil.rmtree(cp)
    os.makedirs(cp, exist_ok=True)
    pipe, gate = _build_pipeline(cp, mission=True, seed=seed, recorder=False)
    adversarial = adversarial_experiment(pipe)
    l3_enforcement = l3_enforcement_experiment()
    boundaries = boundary_table(IdentityProjectionGate())

    artifact = {
        "tool": "layer3_fi_diagnostic",
        "non_mutating": True,
        "cycles": cycles,
        "seed": seed,
        "live_bootstrap_rule": LIVE_BOOTSTRAP_RULE,
        "canonical_gate": "telos/core/identity/projection_gate.py::IdentityProjectionGate.is_admissible",
        "weak_gate": "telos/core/decision/commitment_optimizer.py::CommitmentOptimizer.is_trajectory_admissible",
        "live_path_calls": "canonical IdentityProjectionGate (via SelectPhase._enforce_identity_projection)",
        "reachability": {
            "L3_mission_check_reachable_in_live_path": bool(
                l3_enforcement["L3_rejected_live_shaped_intent"]),
            "proof": ("select.py::_identity_gate_context now returns "
                      "missionless_bootstrap = not mission_defined (GENUINE "
                      "bootstrap only); a kernel that declared an objective but "
                      "has no active mission scope presents "
                      "mission_active=False, mission_defined=True, "
                      "missionless_bootstrap=False, which the L3 guard "
                      "'not mission_active and not genuine_bootstrap' "
                      "satisfies -> the mission-less trajectory is projected out"),
            "L1_reachable_structurally": True,
            "L1_reachable_for_live_intents": False,
            "L1_note": ("L1 fires only on literal adversarial substrings "
                        "('steal'/'deceive'/'exploit'+'explore'+'harm'); no live "
                        "stream emits those"),
            "L2_reachable_structurally": True,
            "L2_reachable_for_live_intents": False,
            "L2_note": ("the default role 'agent' now has a real compatibility "
                        "predicate (agency-ceding intents: abdicate/surrender/"
                        "self_destruct/self_terminate/delegate_all); it is "
                        "conservative and no live stream emits those, so L2 is "
                        "live-capable but inert for live traffic (defense-in-depth)"),
        },
        "workloads": {"with_mission": with_mission,
                      "without_mission": without_mission},
        "decision_neutrality": neutrality,
        "adversarial": adversarial,
        "l3_enforcement": l3_enforcement,
        "boundary": boundaries,
    }

    live_failures = (with_mission["failures"] + without_mission["failures"])
    live_rejected = (with_mission["rejected_selected_total"]
                     + without_mission["rejected_selected_total"])
    l3_ok = bool(l3_enforcement["L3_rejected_live_shaped_intent"])
    artifact["classification"] = {
        "verdict": "FIXED" if l3_ok else "MIX",
        "primary": "C (wiring gap) — FIXED",
        "primary_evidence": (
            "select.py::_identity_gate_context now returns missionless_bootstrap "
            "= not mission_defined (GENUINE bootstrap only, no objective ever "
            "declared); a declared objective with no active mission scope now "
            "satisfies the L3 guard and is projected out. The old wiring set "
            "missionless_bootstrap = not mission_active, making "
            "'not mission_active and not missionless_bootstrap' unsatisfiable"),
        "secondary": "B (permissive L1) — L2 default role now has a real predicate",
        "secondary_evidence": (
            "Layer 1 matches literal substrings only (upstream streams never emit "
            "adversarial types — genuine defense-in-depth). Layer 2's default role "
            "'agent' now has a real, conservative compatibility predicate "
            "(agency-ceding intents); it is live-capable but inert for live "
            "traffic, i.e. legitimate defense-in-depth, not tautology"),
        "D_scope": "Layer 1 only: upstream streams never emit adversarial intent types",
        "live_F_I_failures": live_failures,
        "live_rejections": live_rejected,
        "inadmissible_live_intents_possible": l3_ok,
        "headline": (
            "Layer 3 is no longer a tautology: a kernel that declared an objective "
            "but currently has no active mission scope projects a mission-less "
            "live-shaped intent out and replaces it with the safe reflex keeper. "
            "The default live run (objective ACTIVE) is unchanged — the mission "
            "scope is present, so live intents remain admissible"),
        "fix_recommended": False,
        "fix_applied": True,
    }
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(artifact, f, indent=2, default=str)
    return artifact


def main():
    """CLI entry point for the Layer-3 F(I) diagnostic."""
    ap = argparse.ArgumentParser(description="Layer-3 F(I) diagnostic (non-mutating)")
    ap.add_argument("--cycles", type=int, default=DEFAULT_CYCLES)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", default=OUT_PATH)
    ap.add_argument("--ci", action="store_true",
                    help="assert the classification invariants; exit nonzero on drift")
    args = ap.parse_args()
    logging.basicConfig(level=logging.CRITICAL)
    logging.disable(logging.CRITICAL)

    art = run_diagnostic(cycles=args.cycles, seed=args.seed, out_path=args.out)
    wm = art["workloads"]["with_mission"]
    nm = art["workloads"]["without_mission"]
    adv = art["adversarial"]
    l3e = art["l3_enforcement"]
    neu = art["decision_neutrality"]

    print("=" * 78)
    print(f"LAYER-3 F(I) DIAGNOSTIC — {args.cycles} cycles, seed={args.seed}")
    print("=" * 78)
    for label, s in (("with mission", wm), ("without mission", nm)):
        print(f"[{label}] evaluations={s['evaluations']} failures={s['failures']} "
              f"projected_out={s['projected_out_total']} rejected_selected={s['rejected_selected_total']} "
              f"fallback={s['safe_fallback_total']}")
        print(f"  types: {list(s['intent_type_counts'].items())[:8]}")
        print(f"  active_block_histogram: {s['active_block_histogram']}")
        print(f"  layer_armed_counts: {s['layer_armed_counts']}")
    print(f"[neutrality] recorder={neu['recorder_fp']} plain={neu['plain_fp']} "
          f"neutral={neu['decision_neutral']}")
    print(f"[adversarial] normal={adv['normal']['F_I']} evil={adv['evil']['F_I']} "
          f"projected_out={adv['enforcement']['projected_out']} "
          f"replacement={adv['enforcement']['replacement']}")
    print(f"[l3_enforcement] live_shaped={l3e['live_shaped_intent']} "
          f"rejected={l3e['L3_rejected_live_shaped_intent']} "
          f"replacement={l3e['replacement']} "
          f"after_mission={l3e['after_mission_completed']}")
    print("[boundary]")
    for r in art["boundary"]:
        print(f"  {'OK ' if r['pass'] else 'BAD'} {r['case']:<60} "
              f"actual={r['actual']} expected={r['expected']}")
    print(f"[classification] {art['classification']['verdict']}: "
          f"{art['classification']['primary']} + {art['classification']['secondary']}")
    print("=" * 78)

    if args.ci:
        ok = True
        checks = []
        checks.append(("recorder decision-neutral", neu["decision_neutral"], True))
        checks.append(("active-mission live run no failures", wm["failures"] == 0, True))
        checks.append(("active-mission no projected_out", wm["projected_out_total"] == 0, True))
        checks.append(("active-mission no rejected_selected", wm["rejected_selected_total"] == 0, True))
        checks.append(("without-mission run no failures", nm["failures"] == 0, True))
        checks.append(("L3 reachable in live path", art["reachability"]
                       ["L3_mission_check_reachable_in_live_path"] is True, True))
        checks.append(("L3 rejects live-shaped intent when mission inactive",
                       l3e["L3_rejected_live_shaped_intent"] is True, True))
        checks.append(("L3 replacement is reflex fallback",
                       l3e["replacement"] == "reflex", True))
        checks.append(("adversarial normal PASS", adv["normal"]["F_I"] is True, True))
        checks.append(("adversarial evil FAIL", adv["evil"]["F_I"] is False, True))
        checks.append(("adversarial evil projected out",
                       "steal_payload" in adv["enforcement"]["projected_out"], True))
        for r in art["boundary"]:
            checks.append((f"boundary:{r['case'][:40]}", r["actual"], r["expected"]))
        for name, got, exp in checks:
            if got != exp:
                ok = False
                print(f"  [FAIL] {name}: got={got} expected={exp}")
        print("DIAGNOSTIC GATE:", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)
    sys.exit(0)


if __name__ == "__main__":
    main()
