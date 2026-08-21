"""Run the real TELOS 7-phase pipeline over the 5-idea portfolio."""
import os, tempfile, logging
import numpy as np
logging.basicConfig(level=logging.WARNING)

from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation import CounterfactualEngine
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream, TheoryStream,
)
from telos.core.streams.inquiry_stream import InquiryStream
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
    EvidenceProvenanceValidator,
)
from telos.core.governance.firewall import DecisionFirewall
from telos.ideation.portfolio_sim import PortfolioSimulator, IDEAS, STATE_INDEX
from telos.ideation.concepts import weighted_score

class IdentityAdapter:
    def forward(self, x): return x
    def inverse(self, x): return x
    def intent_to_action(self, intent, state, md):
        if intent is not None and getattr(intent, "params", None) and "action_vector" in intent.params:
            return np.asarray(intent.params["action_vector"], dtype=float)
        return np.zeros_like(np.asarray(state, dtype=float), dtype=float)
    def declared_state_dim(self):
        return None
    @property
    def name(self): return "trust_portfolio"

def build_pipeline(sim, tmpdir):
    pipe = TelosV14Pipeline(PipelineConfig(
        adapter=IdentityAdapter(),
        simulator=sim,
        compute_budget_ms=200.0,
        state_dim=len(sim.context) + 2,
        n_worlds=8, horizon=3,
        checkpoint_path=os.path.join(tmpdir, "checkpoints"),
        knowledge_path=os.path.join(tmpdir, "knowledge.json"),
        ledger_path=os.path.join(tmpdir, "ledger.json"),
        identity_path=os.path.join(tmpdir, "identity.json"),
        pattern_path=os.path.join(tmpdir, "patterns.json"),
        deterministic_seed=42,
        distributed_council_enabled=True,
    ))
    sl = SkillLibrary()
    eng = CounterfactualEngine(sim, seed=42)
    pipe.register_stream(ReflexStream(sl))
    pipe.register_stream(PerceptionStream(sl))
    pipe.register_stream(MemoryStream(sl))
    pipe.register_stream(PlanningStream(sl, sim_engine=eng))
    pipe.register_stream(InquiryStream(sl))
    pipe.register_stream(TheoryStream(sl, theory_builder=getattr(pipe, "_theory_builder", None)))
    pipe.register_validator(RealityValidator())
    pipe.register_validator(ConstraintValidator())
    mem = MemoryAdvisor(sl)
    pipe.register_validator(mem)
    if hasattr(pipe, "infra_manager") and pipe.infra_manager is not None:
        mem.connect(failure_ledger=getattr(pipe.infra_manager, "failures", None),
                    knowledge_graph=getattr(pipe.infra_manager, "knowledge", None))
    pipe.register_validator(MissionDriftDetector(drift_threshold=5.0))
    try:
        pipe.register_validator(EvidenceProvenanceValidator())
    except Exception as e:
        print("  (evidence validator skipped:", e, ")")
    return pipe

def main():
    tmpdir = tempfile.mkdtemp(prefix="telos_portfolio_")
    sim = PortfolioSimulator(idea_subset=list(range(len(IDEAS))))
    pipe = build_pipeline(sim, tmpdir)
    state = np.concatenate([sim.context, np.array([0.0, 0.0])])

    print("=" * 90)
    print("TELOS 7-PHASE PIPELINE :: FIVE-IDEA TRUST/ATTENTION/AI-INFRA PORTFOLIO")
    print("=" * 90)
    print("\n[PERCEIVE] STRUCTURAL REALITY MAP (activation = pressure):")
    for k, i in STATE_INDEX.items():
        print(f"    {k:22s} activation={sim.context[i]:.2f}")

    results = []
    for cycle, idea in enumerate(IDEAS, start=1):
        # run the pipeline once per idea to get real DI/MD + council verdict
        res = pipe.execute(state.copy(), user_name="Prateek")
        trace = res.decision_trace
        di = trace.decision_integrity if trace else 1.0
        md = trace.mission_drift if trace else 0.0
        dv = res.distributed_verdict
        dv_agg = (dv.get("aggregate") if isinstance(dv, dict) else None)
        results.append({
            "key": idea["key"], "name": idea["name"], "pattern": idea["pattern"],
            "axioms": idea["axioms"], "axes": idea["axes"],
            "weighted": weighted_score(idea["axes"]),
            "di": di, "md": md,
            "council_blocked": res.council_blocked,
            "firewall_blocked": res.firewall_blocked,
            "distributed_agg": dv_agg,
        })
        blk = "COUNCIL-BLOCKED" if res.council_blocked else ("FIREWALL-BLOCKED" if res.firewall_blocked else "PASS")
        print(f"\n[cycle {cycle}] SIMULATE+EVALUATE+SELECT+COUNCIL: {idea['name']}")
        print(f"    pattern={idea['pattern']:11s} axioms={','.join(idea['axioms'])}")
        print(f"    composite={weighted_score(idea['axes']):.3f} | DI={di:.3f} | MD={md:.3f} | verdict={blk} | dist_agg={dv_agg}")
    pipe.shutdown()

    ranked = sorted(results, key=lambda r: r["weighted"], reverse=True)
    print("\n" + "=" * 90)
    print("[EVALUATE+SELECT] Ranked by veteran-weighted composite (moat+resilience 1.5x):")
    print("=" * 90)
    for i, r in enumerate(ranked, 1):
        blk = "❌ BLOCKED" if (r["council_blocked"] or r["firewall_blocked"]) else "VALIDATED"
        print(f"  #{i:2d} {r['key']}  {r['name']:45s} w={r['weighted']:.3f} DI={r['di']:.2f} MD={r['md']:.2f} {blk}")
    return results, ranked

if __name__ == "__main__":
    main()
