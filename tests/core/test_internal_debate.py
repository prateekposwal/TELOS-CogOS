"""
InternalDebate (core/council/internal_debate.py) — honest contract coverage.
"""
from telos.core.council.internal_debate import InternalDebate


class TestInternalDebate:
    def test_debate_runs_and_synthesizes(self):
        d = InternalDebate()
        result = d.debate(
            context={"intent_type": "explore", "n_options": 3},
            context_description="select test",
        )
        assert result is not None
        assert hasattr(result, "consensus_level")
        assert hasattr(result, "winning_perspective")
        assert hasattr(result, "synthesis")

    def test_debate_no_perspectives(self):
        d = InternalDebate()
        result = d.debate(context={}, perspective_roles=[])
        assert result.synthesis == "No perspectives available"

    def test_register_perspective(self):
        from telos.core.council.internal_debate import Perspective, PerspectiveRole
        d = InternalDebate()
        p = Perspective(role=PerspectiveRole.SKEPTIC, name="Skeptic",
                        description="challenges consensus", bias_strength=0.5,
                        confidence=0.6)
        d.register_perspective(p)
        result = d.debate(context={}, perspective_roles=[PerspectiveRole.SKEPTIC])
        assert result.perspectives_used  # the registered perspective ran
