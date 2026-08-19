"""
TELOS ideation runner — drives the full 7-phase pipeline over the gaming
ideation task. Produces a real council DI/MD verdict per concept and a
ranked recommendation.

Run:  PYTHONPATH=. python3 -m telos.ideation.runner
"""
import os
import logging
import numpy as np

logging.basicConfig(level=logging.WARNING)

from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation.engine import CounterfactualEngine
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream, TheoryStream,
)
from telos.core.streams.inquiry_stream import InquiryStream
from telos.core.council.validators.reality import RealityValidator
from telos.core.council.validators.constraint import ConstraintValidator
from telos.core.council.validators.memory import MemoryAdvisor
from telos.core.council.validators.mission import MissionDriftDetector

from telos.ideation.simulator import IdeationSimulator, STATE_INDEX, STATE_LABELS
from telos.ideation.concepts import CONCEPTS, weighted_score, STRUCTURAL_INSIGHTS


class IdentityAdapter:
    def forward(self, x): return x
    def inverse(self, x): return x
    def intent_to_action(self, intent, state, md):
        import numpy as _np
        if intent is not None and intent.params and "action_vector" in intent.params:
            return _np.asarray(intent.params["action_vector"], dtype=float)
        return _np.zeros_like(_np.asarray(state, dtype=float), dtype=float)
    @property
    def name(self): return "ideation"


def build_pipeline(sim, tmpdir):
    pipe = TelosV14Pipeline(PipelineConfig(
        adapter=IdentityAdapter(),
        simulator=sim,
        compute_budget_ms=200.0,
        state_dim=10,
        n_worlds=8,
        horizon=3,
        checkpoint_path=os.path.join(tmpdir, "checkpoints"),
        knowledge_path=os.path.join(tmpdir, "knowledge.json"),
        ledger_path=os.path.join(tmpdir, "ledger.json"),
        identity_path=os.path.join(tmpdir, "identity.json"),
        pattern_path=os.path.join(tmpdir, "patterns.json"),
        deterministic_seed=42,
        distributed_council_enabled=False,  # advisory noise; primary council is the verdict
    ))
    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(sim, seed=42)
    pipe.register_stream(ReflexStream(skill_lib))
    pipe.register_stream(PerceptionStream(skill_lib))
    pipe.register_stream(MemoryStream(skill_lib))
    pipe.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))
    pipe.register_stream(InquiryStream(skill_lib))
    pipe.register_stream(TheoryStream(skill_lib, theory_builder=getattr(pipe, '_theory_builder', None)))
    pipe.register_validator(RealityValidator())
    pipe.register_validator(ConstraintValidator())
    mem = MemoryAdvisor(skill_lib)
    pipe.register_validator(mem)
    if hasattr(pipe, 'infra_manager') and pipe.infra_manager is not None:
        mem.connect(failure_ledger=getattr(pipe.infra_manager, 'failures', None),
                    knowledge_graph=getattr(pipe.infra_manager, 'knowledge', None))
    pipe.register_validator(MissionDriftDetector(drift_threshold=5.0))
    return pipe


def main():
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="telos_ideation_")
    sim = IdeationSimulator(concept_subset=list(range(len(CONCEPTS))))
    pipe = build_pipeline(sim, tmpdir)

    state = np.concatenate([sim.context, np.array([0.0, 0.0])])
    print("=" * 78)
    print("TELOS COGNITIVE PIPELINE — Structural Gaming-Industry Ideation")
    print("Frame: industry structure, NOT surface player pain.")
    print("=" * 78)

    print("\n[0] PERCEIVE — the structural reality map a veteran sees:")
    for k, i in STATE_INDEX.items():
        print(f"    {k:26s} activation={sim.context[i]:.2f}")

    results = []
    for cycle, idx in enumerate(sim._subset, start=1):
        concept = CONCEPTS[idx]
        # PERCEIVE - run one full pipeline cycle per concept
        result = pipe.execute(state.copy(), user_name="Prateek")
        trace = result.decision_trace
        di = trace.decision_integrity if trace else 1.0
        md = trace.mission_drift if trace else 0.0
        validated = result.council_blocked is False and result.firewall_blocked is False
        w = weighted_score(concept["axes"])
        results.append({
            "index": idx,
            "name": concept["name"],
            "insight_key": concept["insight_key"],
            "axes": concept["axes"],
            "weighted": w,
            "di": di,
            "md": md,
            "validated": validated,
            "worlds": result.worlds_generated,
            "selected_intent": trace.selected_intent.intent_type if trace and trace.selected_intent else None,
        })
        print(f"\n[cycle {cycle}] SIMULATE+EVALUATE concept #{idx}:  {concept['name']}")
        print(f"    exploits structural insight: {concept['insight_key']}")
        print(f"    veteran composite score (moat+resilience weighted): {w:.3f}")

    pipe.shutdown()

    # [EVALUATE] rank by veteran composite
    ranked = sorted(results, key=lambda r: r["weighted"], reverse=True)

    print("\n" + "=" * 78)
    print("[EVALUATE] Ranked by veteran-weighted composite (moat 1.5x + resilience 1.5x):")
    print("=" * 78)
    for i, r in enumerate(ranked, 1):
        markers = ["moat", "resilience", "fragility"]
        moat = r["axes"]["moat"]
        res = r["axes"]["resilience"]
        flag = "  ⚠ high-fragility" if res < 0.55 else ""
        print(f"  #{i}  {r['name']}")
        print(f"      composite={r['weighted']:.3f} | moat={moat:.2f} | resilience={res:.2f} "
              f"| DI={r['di']:.3f} | MD={r['md']:.3f} | council_validated={r['validated']}{flag}")

    # [COUNCIL] summary verdict
    di_vals = [r["di"] for r in results]
    md_vals = [r["md"] for r in results]
    all_validated = all(r["validated"] for r in results)
    print("\n" + "=" * 78)
    print("[COUNCIL] Primary-council aggregate verdict:")
    print(f"    mean DI = {np.mean(di_vals):.3f} | mean MD = {np.mean(md_vals):.3f} | all_concepts_passed = {all_validated}")

    return ranked, results


if __name__ == "__main__":
    main()
