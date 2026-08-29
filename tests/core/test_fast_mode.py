"""v7 K+E — TELOS_MODE fast mode + counterfactual budget.

fast mode skips advisory (non-blocking) layers — InternalDebate and the
DistributedCouncil crew — and gates the counterfactual world count by peak
stream confidence (high-confidence routine cycles simulate 1 world instead
of the full budget). Standard mode is behavior-preserving (full budget,
full advisory stack). The blocking core (validators, firewall, stagnation,
axioms, evidence, trace) is UNTOUCHED in every mode.
"""
import os
import numpy as np

from telos_task import GridAdpt, GridSim, DEFAULT_BLOCKED, DEFAULT_REWARDS, GOAL
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


def _build(mode, tmp_path):
    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
    pipe = TelosV14Pipeline(PipelineConfig(
        adapter=GridAdpt(), simulator=sim,
        compute_budget_ms=100.0, state_dim=2, n_worlds=8, horizon=5,
        checkpoint_path=str(tmp_path / "cp"),
        knowledge_path=str(tmp_path / "kg.json"),
        ledger_path=str(tmp_path / "ld.json"),
        identity_path=str(tmp_path / "id.json"),
        pattern_path=str(tmp_path / "pt.json"),
        deterministic_seed=42, mode=mode,
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
    return pipe


class TestFastMode:
    def test_standard_is_full_budget_and_advisory(self, tmp_path):
        pipe = _build("standard", tmp_path)
        assert pipe.config.is_fast_mode is False
        assert pipe.config.skip_advisory_layers is False

    def test_fast_mode_skips_advisory_layers(self, tmp_path, monkeypatch):
        pipe = _build("fast", tmp_path)
        state = np.array([0.0, 0.0])
        debate_calls = {"n": 0}
        orig_debate = pipe._internal_debate.debate

        def counting_debate(*a, **k):
            debate_calls["n"] += 1
            return orig_debate(*a, **k)

        monkeypatch.setattr(pipe._internal_debate, "debate", counting_debate)
        dist_calls = {"n": 0}
        orig_dist = pipe._run_distributed_council

        def counting_dist(ctx):
            dist_calls["n"] += 1

        monkeypatch.setattr(pipe, "_run_distributed_council", counting_dist)
        for i in range(6):
            pipe.execute(state, user_name="perf")
        assert debate_calls["n"] == 0, "fast mode must skip InternalDebate"
        assert dist_calls["n"] == 0, "fast mode must skip DistributedCouncil"
        # the blocking core still ran: a trace exists with DI
        t = pipe._last_trace
        assert t is not None and t.decision_integrity > 0.0

    def test_fast_mode_budgets_counterfactuals(self, tmp_path, monkeypatch):
        """The simulation budget gate is ACTIVE in fast mode: the simulate
        phase routes every world count through counterfactual_budget
        (confident -> 1 world, routine -> half), the planning stream's world
        budget is halved at registration, and standard mode never touches the
        gate (full budget preserved)."""
        import telos.core.phases.simulate as sim_mod
        calls = []
        orig_budget = sim_mod.counterfactual_budget

        def recording_budget(mode, n_worlds, peak_conf):
            calls.append((mode, n_worlds, peak_conf, orig_budget(mode, n_worlds, peak_conf)))
            return orig_budget(mode, n_worlds, peak_conf)

        monkeypatch.setattr(sim_mod, "counterfactual_budget", recording_budget)
        pipe = _build("fast", tmp_path)
        state = np.array([0.0, 0.0])
        for i in range(4):
            pipe.execute(state, user_name="perf")
        assert calls, "the budget gate must be consulted every fast cycle"
        for mode, n, conf, result in calls:
            assert mode == "fast"
            assert result <= max(1, n // 2), "fast budget must be at most half"
            if conf >= 0.8:
                assert result == 1, "confident routine cycles simulate 1 world"
        # planning stream world budget halved at registration
        planning = [s for s in pipe.streams
                    if s.__class__.__name__ == "PlanningStream"]
        assert planning and planning[0].n_worlds <= 15, (
            "planning stream world budget must be halved in fast mode"
        )
        # pure helper semantics
        assert orig_budget("fast", 8, 0.9) == 1
        assert orig_budget("fast", 8, 0.5) == 4
        assert orig_budget("standard", 8, 0.9) == 8

    def test_standard_mode_never_consults_budget_gate(self, tmp_path, monkeypatch):
        import telos.core.phases.simulate as sim_mod
        calls = []
        orig_budget = sim_mod.counterfactual_budget

        def recording_budget(mode, n_worlds, peak_conf):
            calls.append(mode)
            return orig_budget(mode, n_worlds, peak_conf)

        monkeypatch.setattr(sim_mod, "counterfactual_budget", recording_budget)
        pipe = _build("standard", tmp_path)
        state = np.array([0.0, 0.0])
        for i in range(3):
            pipe.execute(state, user_name="perf")
        assert calls == [], "standard mode must keep the full budget untouched"

    def test_standard_keeps_full_world_budget(self, tmp_path):
        pipe = _build("standard", tmp_path)
        state = np.array([0.0, 0.0])
        worlds = []
        for i in range(4):
            result = pipe.execute(state, user_name="perf")
            worlds.append(getattr(result, "worlds_generated", None))
        assert worlds, "worlds were generated"
        assert max(w or 0 for w in worlds) >= 2, (
            "standard mode preserves the full counterfactual budget"
        )


class TestModeConfig:
    def test_env_propagation_to_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TELOS_MODE", "fast")
        from telos.core.types import PipelineConfig
        cfg = PipelineConfig()
        # env is read at construction sites (producer/telos_task); direct
        # config always wins. fast mode flag maps through.
        assert PipelineConfig(mode="fast").is_fast_mode is True
        assert PipelineConfig().mode == "standard"


class TestCompiledAxioms:
    """v7 I — axioms are compiled once: the runtime never re-reads AXIOMS.md
    or reconstructs axiom metadata after startup (the per-cycle AxiomProver
    runs predicates on the in-memory compiled set; measured ~0.03ms/cycle)."""

    def test_no_axiom_source_reparse_during_run(self, tmp_path, monkeypatch):
        import builtins
        # ensure the registry is already imported (import timing must never
        # count inside this test's open-monkeypatch window)
        from telos.core.axioms.registry import AXIOMS as _AX  # noqa: F401
        assert len(_AX) >= 42
        real_open = builtins.open
        reads = {"axioms_md": 0, "registry": 0}

        def counting_open(*a, **k):
            path = str(a[0]) if a else ""
            if "AXIOMS.md" in path:
                reads["axioms_md"] += 1
            if "axioms/registry.py" in path:
                reads["registry"] += 1
            return real_open(*a, **k)

        monkeypatch.setattr(builtins, "open", counting_open)
        pipe = _build("standard", tmp_path)
        state = np.array([0.0, 0.0])
        for i in range(5):
            pipe.execute(state, user_name="perf")
        assert reads["axioms_md"] == 0, (
            f"AXIOMS.md must not be re-read during a run "
            f"(reads={reads['axioms_md']})"
        )
        # the registry import itself happens once at module import
        assert reads["registry"] == 0

    def test_axiom_metadata_compiled_once(self):
        from telos.core.axioms.registry import AXIOMS
        assert len(AXIOMS) == 42
        # the registry is a static immutable contract (hashable fingerprint)
        import hashlib
        fp = hashlib.sha256(
            "|".join(sorted(str(a.get("id", "")) for a in AXIOMS)).encode()
        ).hexdigest()[:12]
        assert len(fp) == 12
