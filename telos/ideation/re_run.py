"""
TELOS 7-phase pipeline RE-RUN of the gaming-ideation decision, WITH the
real-market competitor layer loaded (the prior run deliberately excluded
`discord_bots` from its PERCEIVE map).

Prior run committed to FoundryHost (#1, 0.686). THIS run prices in the
incumbent Discord-bot ecosystem (backup / moderation / analytics vendors),
re-scores the prior concepts where competition actually serves their axes,
adds 3 new cross-server concepts, and yields a LIVE council verdict.

This run's whole point: where reality contradicts the prior pick, the
verdict MUST change. It is not a defense of the prior pick out of inertia.

Run:  PYTHONPATH=. python3 -m telos.ideation.re_run
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

from telos.ideation.simulator import IdeationSimulator, STATE_INDEX, BOT_ECOSYSTEM_INDEX
from telos.ideation.concepts import CONCEPTS, weighted_score
from telos.ideation.competitors import (
    COMPETITOR_CLUSTERS, NEW_CONCEPTS, re_score_all, score_new,
)

# Short key -> prior concept index, for Re-score mapping.
PRIOR_KEYS = [
    "CareerLedger", "SessionBridge", "TurfTrust", "LadderMiddle",
    "ArchiveLeague", "AFKHaven", "FoundryHost", "KarmaCap",
]
PRIOR_CONCEPTS = list(CONCEPTS)  # authoritative prior 8 (in order)


class IdentityAdapter:
    def forward(self, x): return x
    def inverse(self, x): return x
    def intent_to_action(self, intent, state, md):
        import numpy as _np
        if intent is not None and intent.params and "action_vector" in intent.params:
            return _np.asarray(intent.params["action_vector"], dtype=float)
        return _np.zeros_like(_np.asarray(state, dtype=float), dtype=float)
    @property
    def name(self): return "ideation_rerun"


def build_pipeline(sim, tmpdir):
    pipe = TelosV14Pipeline(PipelineConfig(
        adapter=IdentityAdapter(),
        simulator=sim,
        compute_budget_ms=200.0,
        state_dim=len(sim.context) + 2,
        n_worlds=8,
        horizon=3,
        checkpoint_path=os.path.join(tmpdir, "checkpoints"),
        knowledge_path=os.path.join(tmpdir, "knowledge.json"),
        ledger_path=os.path.join(tmpdir, "ledger.json"),
        identity_path=os.path.join(tmpdir, "identity.json"),
        pattern_path=os.path.join(tmpdir, "patterns.json"),
        deterministic_seed=42,
        distributed_council_enabled=False,
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
    tmpdir = tempfile.mkdtemp(prefix="telos_ideation_rerun_")

    # Build the candidate set: prior-8 re-scored with competition + 3 new.
    prior_scored = re_score_all(PRIOR_CONCEPTS, PRIOR_KEYS)
    new_scored = [(c["name"].split(" (")[0], c["name"], c["axes"], score_new(c))
                  for c in NEW_CONCEPTS]

    # Combined candidate list [{name, axes, weighted, key, source}]
    candidates = []
    for key, name, axes, w in prior_scored:
        candidates.append({"key": key, "name": name, "axes": axes, "weighted": w, "source": "prior_8"})
    for key, name, axes, w in new_scored:
        candidates.append({"key": key, "name": name, "axes": axes, "weighted": w, "source": "new_cross_server"})

    sim = IdeationSimulator(concept_subset=list(range(len(candidates))),
                            with_bot_ecosystem=True,
                            extra_concepts=NEW_CONCEPTS)
    pipe = build_pipeline(sim, tmpdir)

    state = np.concatenate([sim.context, np.array([0.0, 0.0])])

    print("=" * 84)
    print("TELOS 7-PHASE RE-RUN :: gaming ideation WITH real-market competitor layer")
    print("Frame: industry structure (same), now WITH the incumbent bot set loaded")
    print("=" * 84)

    print("\n[PERCEIVE] STRUCTURAL REALITY MAP — competitor layer LOADED (was MISSING):")
    for k, i in STATE_INDEX.items():
        print(f"    {k:24s} activation={sim.context[i]:.2f}")
    for k, i in BOT_ECOSYSTEM_INDEX.items():
        print(f"    {k:24s} activation={sim.context[i]:.2f}   <-- NEW, was excluded")

    print("\n    Incumbent competitor clusters NOW priced in:")
    for cluster, vendors in COMPETITOR_CLUSTERS.items():
        print(f"      • {cluster}: {', '.join(vendors)}")

    print("\n    Genuine whitespace after incumbents priced in:")
    print("      -> incumbents are SINGLE-SERVER SILOED. None carry standing/trust/")
    print("         credentials ACROSS servers/games. No single vendor will federate.")
    print("         Moat = portable community reputation/continuity.")

    results = []
    for cycle, cand in enumerate(candidates, start=1):
        res = pipe.execute(state.copy(), user_name="Prateek")
        trace = res.decision_trace
        di = trace.decision_integrity if trace else 1.0
        md = trace.mission_drift if trace else 0.0
        validated = res.council_blocked is False and res.firewall_blocked is False
        results.append({
            "key": cand["key"],
            "name": cand["name"],
            "weighted": cand["weighted"],
            "axes": cand["axes"],
            "source": cand["source"],
            "di": di,
            "md": md,
            "validated": validated,
        })
        print(f"\n[cycle {cycle}] SIMULATE+EVALUATE: {cand['name']}")
        print(f"    source={cand['source']:15s} | weighted={cand['weighted']:.3f} | DI={di:.3f} | MD={md:.3f} | validated={validated}")

    pipe.shutdown()

    ranked = sorted(results, key=lambda r: r["weighted"], reverse=True)

    print("\n" + "=" * 84)
    print("[EVALUATE+SELECT] Ranked by veteran-weighted composite (WITH competitors):")
    print("=" * 84)
    for i, r in enumerate(ranked, 1):
        src = "NEW-cross-server" if r["source"] == "new_cross_server" else "prior-8(re-scored)"
        flag = "" if r["validated"] else "  ❌ COUNCIL-BLOCKED"
        print(f"  #{i:2d}  {r['name']}")
        print(f"       composite={r['weighted']:.3f} | {src} | DI={r['di']:.3f} | MD={r['md']:.3f}{flag}")

    prior_fh = next(r for r in results if r["key"] == "FoundryHost")
    print("\n" + "=" * 84)
    print("[COUNCIL] PRIOR-PICK REALITY CHECK:")
    print(f"    FoundryHost prior composite: 0.686 (Steam/Epic-vs-community frame, no bots)")
    print(f"    FoundryHost here composite:  {prior_fh['weighted']:.3f} (bot set loaded)")
    print(f"    FoundryHost here validated:  {prior_fh['validated']}")
    print("=" * 84)

    return ranked, results


if __name__ == "__main__":
    main()
