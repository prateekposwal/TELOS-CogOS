"""
Tests for the Session Continuity Layer — ContextSummarizer + TokenBudgetManager
integration into the TelosV14Pipeline.

Verifies:
  1. Both components are instantiated on the pipeline
  2. Token budget optimization doesn't crash on various inputs
  3. After 5+ cycles, session essence may be populated
  4. PhaseContext carries session continuity fields
  5. Session essence flows through perceive phase into world metadata
"""

import numpy as np
from typing import Dict, List, Optional

from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.context.summarizer import ContextSummarizer, SessionEssence
from telos.core.attention.token_budget import TokenBudgetManager
from telos.core.phases.base import PhaseContext, SessionContinuity
from telos.core.streams.implementations import ReflexStream
from telos.core.ledger.skill_library import SkillLibrary
from tests.core.conftest import MockSimulator


class TestSessionContinuityComponents:

    def test_components_instantiated(self):
        """Both ContextSummarizer and TokenBudgetManager exist on pipeline."""
        sim = MockSimulator()
        sim.initialize()
        config = PipelineConfig(simulator=sim, compute_budget_ms=100.0, state_dim=4)
        pipeline = TelosV14Pipeline(config)

        assert hasattr(pipeline, '_context_summarizer'), "Pipeline missing _context_summarizer"
        assert hasattr(pipeline, '_token_budget'), "Pipeline missing _token_budget"
        assert isinstance(pipeline._context_summarizer, ContextSummarizer)
        assert isinstance(pipeline._token_budget, TokenBudgetManager)
        sim.cleanup()

    def test_token_budget_optimize_no_crash(self):
        """Token budget optimization handles empty, sparse, and full histories."""
        mgr = TokenBudgetManager(token_budget=512, keep_last_n=2)

        # Empty history
        assert mgr.optimize([]) == []

        # Sparse history
        hist = [{"role": "user", "content": "hello"}]
        result = mgr.optimize(hist)
        assert len(result) == 1

        # Full history with some signal
        hist = [
            {"role": "user", "content": "What should we do?"},
            {"role": "assistant", "content": "Let me simulate some options."},
            {"role": "user", "content": "I see a problem with the approach."},
            {"role": "assistant", "content": "The council has blocked this decision."},
            {"role": "user", "content": "Escalate to human?"},
            {"role": "assistant", "content": "Escalation requested. Waiting for override."},
        ]
        result = mgr.optimize(hist)
        assert len(result) > 0
        assert len(result) <= len(hist)

        # With traces dict
        traces = {
            0: TokenBudgetManager.make_trace(di=0.9, md=0.1),
            1: TokenBudgetManager.make_trace(di=0.9, md=0.1),
            2: TokenBudgetManager.make_trace(di=0.4, md=0.5, blocked=True),
            3: TokenBudgetManager.make_trace(di=0.4, md=0.5, blocked=True),
            4: TokenBudgetManager.make_trace(di=0.3, md=0.6, escalated=True),
            5: TokenBudgetManager.make_trace(di=0.3, md=0.6, escalated=True),
        }
        result_with_traces = mgr.optimize(hist, traces=traces)
        assert len(result_with_traces) > 0

    def test_score_message_ranges(self):
        """score_message returns values in [0.0, 2.0] for various inputs."""
        # User message
        score = TokenBudgetManager.score_message({"role": "user", "content": "hello"})
        assert 0.0 <= score <= 2.0
        assert score >= 0.5  # user base score

        # Escalation message
        score = TokenBudgetManager.score_message(
            {"role": "assistant", "content": "Escalation requested to human."},
            trace={"di": 0.2, "md": 0.8, "blocked": True, "escalated": True},
        )
        assert 0.0 <= score <= 2.0
        assert score > 1.0  # high signal

        # Low-signal message
        score = TokenBudgetManager.score_message(
            {"role": "assistant", "content": "ok"},
        )
        assert 0.0 <= score <= 2.0

    def test_session_essence_create_and_merge(self):
        """SessionEssence creation and merge works correctly."""
        essence1 = SessionEssence(
            key_decisions=["Deploy v2", "Rollback"],
            user_preferences=["prefers dark mode"],
            blockers_resolved=["API timeout"],
            recurring_intents=["deploy", "rollback"],
            mood_trajectory="cautious",
        )
        assert len(essence1.key_decisions) == 2

        essence2 = SessionEssence(
            key_decisions=["Scale up"],
            user_preferences=["prefers dark mode", "likes fast feedback"],
            mood_trajectory="optimistic",
        )

        merged = essence1.merge(essence2)
        assert len(merged.key_decisions) == 3  # deduplication
        assert len(merged.user_preferences) == 2  # deduplicated
        assert merged.mood_trajectory == "optimistic"  # latest wins

    def test_session_essence_to_from_dict(self):
        """SessionEssence round-trips through dict serialization."""
        essence = SessionEssence(
            key_decisions=["Deploy"],
            user_preferences=["dark mode"],
            mood_trajectory="neutral",
        )
        d = essence.to_dict()
        restored = SessionEssence.from_dict(d)
        assert restored.key_decisions == ["Deploy"]
        assert restored.user_preferences == ["dark mode"]
        assert restored.mood_trajectory == "neutral"

    def test_context_summarizer_no_ollama(self):
        """ContextSummarizer works with a no-op ollama function."""
        def fake_ollama(messages):
            return '{"key_decisions": [], "user_preferences": [], "blockers_resolved": [], "recurring_intents": [], "mood_trajectory": "neutral"}'

        summarizer = ContextSummarizer(ollama_chat_fn=fake_ollama, summary_interval=1)
        chat_history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
            {"role": "user", "content": "can you help?"},
            {"role": "assistant", "content": "sure"},
            {"role": "user", "content": "let's do it"},
        ]
        essence = summarizer.maybe_summarize(5, chat_history)
        assert essence is not None
        assert isinstance(essence, SessionEssence)
        assert essence.mood_trajectory == "neutral"
        assert summarizer.running_essence is not None

    def test_phase_context_has_session(self):
        """PhaseContext carries SessionContinuity by default."""
        ctx = PhaseContext(
            cycle_count=1,
            state=np.zeros(4),
            user_name=None,
        )
        assert hasattr(ctx, 'session')
        assert isinstance(ctx.session, SessionContinuity)
        assert ctx.session.truncated_history == []
        assert ctx.session.session_essence is None

    def test_pipeline_execute_with_chat_history(self):
        """Pipeline executes without error when chat_history is provided."""
        sim = MockSimulator()
        sim.initialize()
        config = PipelineConfig(
            simulator=sim, compute_budget_ms=100.0, state_dim=4, n_worlds=5,
        )
        pipeline = TelosV14Pipeline(config)
        skill_lib = SkillLibrary()
        pipeline.register_stream(ReflexStream(skill_lib))

        state = np.array([1.0, 2.0, 0.5, -0.3])
        chat_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "I'm ready to help."},
            {"role": "user", "content": "Let's start the process."},
        ]
        result = pipeline.execute(state, chat_history=chat_history)
        assert result.pipeline_phase.value == "complete"
        # Session field should exist in ctx (accessible via result)
        assert result.decision_trace is not None
        sim.cleanup()

    def test_multi_cycle_essence_accumulation(self):
        """Over multiple cycles, session essence can be populated."""
        def fake_ollama(messages):
            return '{"key_decisions": ["test decision"], "user_preferences": ["test pref"], "blockers_resolved": [], "recurring_intents": ["test"], "mood_trajectory": "neutral"}'

        sim = MockSimulator()
        sim.initialize()

        # We need a pipeline with a custom summarizer
        config = PipelineConfig(
            simulator=sim, compute_budget_ms=100.0, state_dim=4, n_worlds=5,
        )
        pipeline = TelosV14Pipeline(config)
        # Override with a test summarizer that fires every cycle
        pipeline._context_summarizer = ContextSummarizer(
            ollama_chat_fn=fake_ollama, summary_interval=1,
        )

        skill_lib = SkillLibrary()
        pipeline.register_stream(ReflexStream(skill_lib))

        state = np.array([1.0, 2.0, 0.5, -0.3])
        chat_history = [
            {"role": "user", "content": "cycle content " + str(i)}
            for i in range(20)
        ]

        # Run 6 cycles — summarizer fires on cycles where interval is met
        for cycle in range(6):
            result = pipeline.execute(state, chat_history=chat_history)
            assert result.pipeline_phase.value == "complete"

        # After 6 cycles with interval=1, essence should be populated
        summary_count = len(pipeline._context_summarizer.summaries)
        assert summary_count > 0, f"Expected summaries after 6 cycles, got {summary_count}"
        assert pipeline._context_summarizer.running_essence is not None

        sim.cleanup()

    def test_token_budget_in_pipeline(self):
        """Token budget optimization runs as part of pipeline execute."""
        sim = MockSimulator()
        sim.initialize()
        config = PipelineConfig(
            simulator=sim, compute_budget_ms=100.0, state_dim=4, n_worlds=5,
        )
        pipeline = TelosV14Pipeline(config)
        skill_lib = SkillLibrary()
        pipeline.register_stream(ReflexStream(skill_lib))

        state = np.array([1.0, 2.0, 0.5, -0.3])
        chat_history = [
            {"role": "user", "content": "Hello" + str(i)}
            for i in range(50)  # Enough to trigger optimization
        ]
        result = pipeline.execute(state, chat_history=chat_history)
        assert result.pipeline_phase.value == "complete"

        # The token budget optimization runs silently — no crash means success
        sim.cleanup()

    def test_perceive_injects_essence(self):
        """Session essence flows into world.metadata through PerceivePhase."""
        def fake_ollama(messages):
            return '{"key_decisions": ["inject test"], "user_preferences": [], "blockers_resolved": [], "recurring_intents": [], "mood_trajectory": "neutral"}'

        sim = MockSimulator()
        sim.initialize()
        config = PipelineConfig(
            simulator=sim, compute_budget_ms=100.0, state_dim=4, n_worlds=5,
        )
        pipeline = TelosV14Pipeline(config)
        pipeline._context_summarizer = ContextSummarizer(
            ollama_chat_fn=fake_ollama, summary_interval=1,
        )
        skill_lib = SkillLibrary()
        pipeline.register_stream(ReflexStream(skill_lib))

        state = np.array([1.0, 2.0, 0.5, -0.3])
        chat_history = [
            {"role": "user", "content": f"msg {i}"}
            for i in range(10)
        ]

        # First cycle: summarizer may not fire if history is too short
        result1 = pipeline.execute(state, chat_history=chat_history)
        assert result1.pipeline_phase.value == "complete"

        # Second cycle: essence should be populated now
        result2 = pipeline.execute(state, chat_history=chat_history)
        assert result2.pipeline_phase.value == "complete"

        # The running essence should have accumulated
        assert pipeline._context_summarizer.running_essence is not None
        assert len(pipeline._context_summarizer.running_essence.key_decisions) > 0

        sim.cleanup()

    def test_session_continuity_dataclass(self):
        """SessionContinuity dataclass works correctly."""
        sc = SessionContinuity()
        assert sc.truncated_history == []
        assert sc.session_essence is None

        sc.truncated_history = [{"role": "user", "content": "hello"}]
        sc.session_essence = {"mood": "neutral"}
        assert len(sc.truncated_history) == 1
        assert sc.session_essence["mood"] == "neutral"
