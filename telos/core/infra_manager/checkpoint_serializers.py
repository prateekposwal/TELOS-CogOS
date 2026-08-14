"""
Per-subsystem serializers for CheckpointManager.

Each subsystem gets a `dump()` / `load()` pair that knows how to
serialize and restore that component's state. The CheckpointManager
orchestrates them without knowing the internals.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger('telos_checkpoint')


# ── Ledger (WorldLedger user profiles) ──

def dump_ledger(world_ledger: Any) -> dict:
    from telos.core.ledger.world_ledger import EntityRecord, UserProfile
    return {
        "entity_count": len(getattr(world_ledger, '_records', {})),
        "user_profiles": [
            {
                "name": p.name, "first_seen": p.first_seen,
                "last_seen": p.last_seen, "total_interactions": p.total_interactions,
                "trust_level": p.trust_level, "typical_intents": p.typical_intents,
                "last_intent": p.last_intent,
                "relationship_summary": p.relationship_summary,
                "interaction_history": p.interaction_history[-20:],
            }
            for p in getattr(world_ledger, '_user_profiles', {}).values()
        ],
    }


def load_ledger(data: dict, ledger: Any) -> None:
    from telos.core.ledger.world_ledger import UserProfile
    if not ledger or not hasattr(ledger, '_user_profiles'):
        return
    for up in data.get("user_profiles", []):
        ledger._user_profiles[up["name"]] = UserProfile(
            name=up["name"], first_seen=up.get("first_seen", 0),
            last_seen=up.get("last_seen", 0),
            total_interactions=up.get("total_interactions", 0),
            trust_level=up.get("trust_level", 0.5),
            typical_intents=up.get("typical_intents", []),
            last_intent=up.get("last_intent", ""),
            relationship_summary=up.get("relationship_summary", "new_user"),
            interaction_history=up.get("interaction_history", []),
        )


# ── SkillLibrary ──

def dump_skills(skill_library: Any) -> dict:
    data: dict = {"skills": [], "archived": []}
    if hasattr(skill_library, 'skills'):
        for sid, s in skill_library.skills.items():
            data["skills"].append(dict(
                skill_id=s.skill_id, fingerprint=s.fingerprint,
                utility_score=s.utility_score,
                last_matched_cycle=s.last_matched_cycle,
                metadata=s.metadata,
            ))
    if hasattr(skill_library, '_archived'):
        for s in skill_library._archived:
            data["archived"].append(dict(
                skill_id=s.skill_id, fingerprint=s.fingerprint,
                utility_score=s.utility_score,
                last_matched_cycle=s.last_matched_cycle,
                metadata=s.metadata,
            ))
    return data


def load_skills(data: dict, skill_library: Any) -> None:
    from telos.core.ledger.skill_library import Skill
    for sd in data.get("skills", []):
        skill_library.index_skill(Skill(
            skill_id=sd["skill_id"], fingerprint=sd.get("fingerprint", ""),
            trajectory=None,
            utility_score=sd.get("utility_score", 0.5),
        ))
        skill_library.skills[sd["skill_id"]].last_matched_cycle = sd.get("last_matched_cycle", 0)
    for sd in data.get("archived", []):
        s = Skill(
            skill_id=sd["skill_id"], fingerprint=sd.get("fingerprint", ""),
            trajectory=None,
            utility_score=sd.get("utility_score", 0.5),
        )
        s.last_matched_cycle = sd.get("last_matched_cycle", 0)
        skill_library._archived.append(s)


# ── StreamCalibrator ──

def dump_calibrator(stream_calibrator: Any) -> dict:
    data: dict = {}
    if hasattr(stream_calibrator, '_calibrations'):
        data["calibrations"] = {
            name: {
                "stream_name": cal.stream_name,
                "total_calls": cal.total_calls,
                "accurate_calls": cal.accurate_calls,
                "confidence_history": cal.confidence_history,
                "drift_history": cal.drift_history,
                "historical_reliability": cal.historical_reliability,
                "influence_weight": cal.influence_weight,
                "last_calibrated": cal.last_calibrated,
            }
            for name, cal in stream_calibrator._calibrations.items()
        }
    if hasattr(stream_calibrator, '_weights'):
        data["weights"] = dict(stream_calibrator._weights)
    if hasattr(stream_calibrator, '_accuracy'):
        data["accuracy"] = dict(stream_calibrator._accuracy)
    if hasattr(stream_calibrator, '_total_calls'):
        data["total_calls"] = dict(stream_calibrator._total_calls)
    return data


def load_calibrator(data: dict, calibrator: Any) -> None:
    if "calibrations" in data and hasattr(calibrator, '_calibrations'):
        from telos.core.infra_manager.stream_calibrator import StreamCalibration
        for name, cal_dict in data["calibrations"].items():
            calibrator._calibrations[name] = StreamCalibration(
                stream_name=cal_dict.get("stream_name", name),
                total_calls=cal_dict.get("total_calls", 0),
                accurate_calls=cal_dict.get("accurate_calls", 0),
                confidence_history=cal_dict.get("confidence_history", []),
                drift_history=cal_dict.get("drift_history", []),
                historical_reliability=cal_dict.get("historical_reliability", 0.5),
                influence_weight=cal_dict.get("influence_weight", 1.0),
                last_calibrated=cal_dict.get("last_calibrated", 0.0),
            )
    elif hasattr(calibrator, '_weights') and "weights" in data:
        for k, v in data["weights"].items():
            calibrator._weights[k] = v
        if hasattr(calibrator, '_accuracy') and "accuracy" in data:
            for k, v in data["accuracy"].items():
                calibrator._accuracy[k] = v
        if hasattr(calibrator, '_total_calls') and "total_calls" in data:
            for k, v in data["total_calls"].items():
                calibrator._total_calls[k] = v


# ── FailureLedger ──

def dump_failures(failure_ledger: Any) -> list:
    if not hasattr(failure_ledger, '_failures'):
        return []
    return [
        {
            "cycle": r.cycle, "failure_type": r.failure_type,
            "severity": r.severity, "root_cause": r.root_cause,
            "blocked_by": r.blocked_by,
            "decision_integrity": r.decision_integrity,
            "mission_drift": r.mission_drift,
        }
        for r in failure_ledger._failures[-50:]
    ]


def load_failures(data: list, failures: Any) -> None:
    from telos.core.infra_manager.failure_ledger import FailureRecord
    if not data or not hasattr(failures, '_failures'):
        return
    for fd in data:
        failures._failures.append(FailureRecord(
            failure_id=f"restored_{fd.get('cycle', 0)}_{len(failures._failures)}",
            cycle=fd.get("cycle", 0), timestamp=0,
            failure_type=fd.get("failure_type", "restored"),
            severity=fd.get("severity", 0.5),
            root_cause=fd.get("root_cause", ""),
            blocked_by=fd.get("blocked_by"),
            decision_integrity=fd.get("decision_integrity", 1.0),
            mission_drift=fd.get("mission_drift", 0.0),
        ))


# ── MissionPolicy ──

def dump_policy(mission_policy: Any) -> dict:
    data: dict = {}
    if hasattr(mission_policy, '_current'):
        c = mission_policy._current
        data["current"] = {
            "mission_name": c.mission_name,
            "risk_tolerance": c.risk_tolerance,
            "exploration_budget": c.exploration_budget,
            "ambition_level": c.ambition_level,
            "drift_tolerance": c.drift_tolerance,
            "recovery_mode": c.recovery_mode,
        }
        data["domain_pulls"] = dict(getattr(mission_policy, '_domain_pulls', {}))
        data["domain_rewards"] = dict(getattr(mission_policy, '_domain_rewards', {}))
    elif hasattr(mission_policy, '_risk_tolerance'):
        data["risk_tolerance"] = mission_policy._risk_tolerance
    return data


def load_policy(data: dict, policy: Any) -> None:
    from telos.core.infra_manager.mission_policy import MissionPolicy
    if "current" in data:
        c = data["current"]
        policy.set_policy(MissionPolicy(
            mission_name=c.get("mission_name", "default"),
            risk_tolerance=c.get("risk_tolerance", 0.3),
            exploration_budget=c.get("exploration_budget", 0.3),
            ambition_level=c.get("ambition_level", 0.5),
            drift_tolerance=c.get("drift_tolerance", 5.0),
            recovery_mode=c.get("recovery_mode", False),
        ))
        pulls = data.get("domain_pulls", {})
        rewards = data.get("domain_rewards", {})
        if pulls:
            policy._domain_pulls = dict(pulls)
        if rewards:
            policy._domain_rewards = {k: float(v) for k, v in rewards.items()}
    elif hasattr(policy, '_risk_tolerance') and "risk_tolerance" in data:
        policy._risk_tolerance = data["risk_tolerance"]


# ── KnowledgeGraph ──

def dump_knowledge(knowledge_graph: Any) -> dict:
    if knowledge_graph is None or not hasattr(knowledge_graph, '_nodes'):
        return {}
    return {
        "nodes": {
            nid: {
                "node_id": n.node_id, "domain": n.domain,
                "approach": n.approach, "outcome": n.outcome,
                "failure_reason": n.failure_reason, "tags": n.tags,
                "params": n.params, "timestamp": n.timestamp,
                "activation": n.activation, "access_count": n.access_count,
                "provenance": n.provenance,
            }
            for nid, n in knowledge_graph._nodes.items()
        },
        "archived_nodes": {
            nid: {
                "node_id": n.node_id, "domain": n.domain,
                "approach": n.approach, "outcome": n.outcome,
                "failure_reason": n.failure_reason, "tags": n.tags,
                "params": n.params, "timestamp": n.timestamp,
                "activation": 0.0, "access_count": n.access_count,
                "provenance": n.provenance,
            }
            for nid, n in getattr(knowledge_graph, '_archived_nodes', {}).items()
        } if hasattr(knowledge_graph, '_archived_nodes') else {},
        "cycle": getattr(knowledge_graph, '_cycle', 0),
        "edges": {
            eid: {
                "edge_id": e.edge_id, "src": e.src, "dst": e.dst,
                "edge_type": e.edge_type, "weight": e.weight,
                "metadata": e.metadata, "timestamp": e.timestamp,
            }
            for eid, e in getattr(knowledge_graph, '_edges', {}).items()
        } if hasattr(knowledge_graph, '_edges') else {},
    }


def load_knowledge(data: dict, kg: Any) -> None:
    from telos.core.knowledge.graph import ProjectNode
    nodes = data.get("nodes", {})
    if not nodes or not hasattr(kg, '_nodes'):
        return
    for nid, nd in nodes.items():
        kg._nodes[nid] = ProjectNode(
            node_id=nd.get("node_id", nid), domain=nd.get("domain", ""),
            approach=nd.get("approach", ""), outcome=nd.get("outcome", 0.0),
            failure_reason=nd.get("failure_reason"), tags=nd.get("tags", []),
            params=nd.get("params", {}), timestamp=nd.get("timestamp", 0),
            activation=nd.get("activation", 1.0), access_count=nd.get("access_count", 0),
            provenance=nd.get("provenance", {}),
        )
    kg._cycle = data.get("cycle", 0)
    archived = data.get("archived_nodes", {})
    if archived and hasattr(kg, '_archived_nodes'):
        for nid, nd in archived.items():
            kg._archived_nodes[nid] = ProjectNode(
                node_id=nd.get("node_id", nid), domain=nd.get("domain", ""),
                approach=nd.get("approach", ""), outcome=nd.get("outcome", 0.0),
                failure_reason=nd.get("failure_reason"), tags=nd.get("tags", []),
                params=nd.get("params", {}), timestamp=nd.get("timestamp", 0),
                activation=0.0, access_count=nd.get("access_count", 0),
                provenance=nd.get("provenance", {}),
            )
    if hasattr(kg, '_edges'):
        from telos.core.knowledge.graph import Edge
        for eid, ed in data.get("edges", {}).items():
            kg._edges[eid] = Edge(
                edge_id=ed.get("edge_id", eid), src=ed.get("src", ""),
                dst=ed.get("dst", ""), edge_type=ed.get("edge_type", "related"),
                weight=ed.get("weight", 1.0), metadata=ed.get("metadata", {}),
                timestamp=ed.get("timestamp", 0.0),
            )
            if ed.get("src") and ed.get("dst"):
                kg._adjacency[ed["src"]].add(ed["dst"])
                kg._adjacency[ed["dst"]].add(ed["src"])


# ── SimEngine ──

def dump_sim_engine(sim_engine: Any) -> list:
    if sim_engine is None or not hasattr(sim_engine, '_last_options'):
        return []
    return [
        {
            "score": opt.score, "rank": opt.rank,
            "world_tag": getattr(opt, 'world_tag', None),
            "metadata": getattr(opt, 'metadata', {}),
        }
        for opt in (sim_engine._last_options or [])
    ]


# ── PlanningHorizon ──

def dump_planning_horizon(planning_horizon: Any) -> dict:
    data: dict = {}
    if planning_horizon is None:
        return data
    if hasattr(planning_horizon, 'remaining_steps'):
        data["remaining_steps"] = planning_horizon.remaining_steps
    if hasattr(planning_horizon, 'current_plan'):
        data["current_plan"] = planning_horizon.current_plan
    return data


# ── DecisionTrace ──

def dump_trace(decision_trace: Any) -> Optional[dict]:
    if not decision_trace:
        return None
    td = decision_trace.to_dict() if hasattr(decision_trace, 'to_dict') else {}
    return {
        "cycle_id": td.get("cycle_id"),
        "decision_integrity": td.get("decision_integrity"),
        "mission_drift": td.get("mission_drift"),
        "council_validated": td.get("council_validated"),
        "selected_intent": td.get("selected_intent"),
    }

# ── Session Continuity ──

def load_session_essence(data: Optional[Dict]) -> Optional[Dict]:
    """Load session essence from checkpoint data."""
    return data or {}


def load_truncated_history(data: Optional[List[Dict]]) -> List[Dict]:
    """Load truncated history from checkpoint data."""
    return data or []
