"""Tests for ActiveForgetting — deliberate belief examination and the
retain/weaken/archive/delete lifecycle."""

import time

from telos.core.memory.active_forgetting import (
    ActiveForgetting,
    Belief,
    BeliefType,
    ForgettingAction,
    ForgettingRecord,
)


class TestEnumsAndBelief:
    def test_belief_type_values(self):
        assert BeliefType.FACTUAL.value == "factual"
        assert BeliefType.SELF.value == "self"
        assert BeliefType.PROCEDURAL.value == "procedural"
        assert BeliefType.TEMPORAL.value == "temporal"
        assert BeliefType.SOCIAL.value == "social"
        assert BeliefType.EPISTEMIC.value == "epistemic"

    def test_forgetting_action_values(self):
        assert ForgettingAction.RETAIN.value == "retain"
        assert ForgettingAction.WEAKEN.value == "weaken"
        assert ForgettingAction.ARCHIVE.value == "archive"
        assert ForgettingAction.DELETE.value == "delete"

    def test_evidential_balance(self):
        b = Belief(id="b1", description="d", type=BeliefType.FACTUAL,
                   confidence=0.5)
        assert b.evidential_balance == 0.0
        b.evidence_for = 5
        b.evidence_against = 1
        assert b.evidential_balance == (5 - 1) / 6

    def test_survival_rate(self):
        b = Belief(id="b1", description="d", type=BeliefType.FACTUAL,
                   confidence=0.5)
        assert b.survival_rate == 1.0
        b.examination_history = [True, True, False]
        assert b.survival_rate == 2 / 3


class TestRegistry:
    def test_core_beliefs_registered(self):
        af = ActiveForgetting()
        assert af.total_beliefs == 7

    def test_register_belief_creates_unique_beliefs(self):
        af = ActiveForgetting()
        bid1 = af.register_belief("The sky is blue", BeliefType.FACTUAL, 0.9)
        bid2 = af.register_belief("The sky is blue", BeliefType.FACTUAL, 0.9)
        assert isinstance(bid1, str) and bid1.startswith("blf_")
        # ids embed time.time(), so each registration is distinct (real behavior)
        assert bid1 != bid2
        assert af.total_beliefs == 9

    def test_strengthen(self):
        af = ActiveForgetting()
        bid = af.register_belief("Gravity pulls down", BeliefType.FACTUAL, 0.5)
        assert af.strengthen(bid, amount=0.2) is True
        b = af._beliefs[bid]
        assert b.confidence == 0.7
        assert b.evidence_for == 1

    def test_strengthen_clamps_at_one(self):
        af = ActiveForgetting()
        bid = af.register_belief("Gravity", BeliefType.FACTUAL, 0.99)
        af.strengthen(bid, amount=0.1)
        assert af._beliefs[bid].confidence == 1.0

    def test_weaken(self):
        af = ActiveForgetting()
        bid = af.register_belief("Gravity", BeliefType.FACTUAL, 0.5)
        assert af.weaken(bid, amount=0.2) is True
        assert af._beliefs[bid].confidence == 0.3
        assert af._beliefs[bid].evidence_against == 1

    def test_strengthen_inactive_returns_false(self):
        af = ActiveForgetting()
        bid = af.register_belief("Gravity", BeliefType.FACTUAL, 0.5)
        af.examine(bid, cycle=1, force_action=ForgettingAction.ARCHIVE)
        assert af.strengthen(bid) is False
        assert af.weaken(bid) is False

    def test_strengthen_unknown_returns_false(self):
        af = ActiveForgetting()
        assert af.strengthen("missing") is False

    def test_use_belief_updates_cycle(self):
        af = ActiveForgetting()
        bid = af.register_belief("Gravity", BeliefType.FACTUAL, 0.5)
        af.use_belief(bid, cycle=42)
        b = af._beliefs[bid]
        assert b.last_used_cycle == 42
        assert b.staleness_cycles == 0


class TestSelection:
    def test_least_used_selects_oldest(self):
        af = ActiveForgetting()
        old = af.register_belief("old", BeliefType.FACTUAL, 0.5)
        new = af.register_belief("new", BeliefType.FACTUAL, 0.5)
        # registered beliefs are newer than the 7 genesis core beliefs, so
        # pin last_used explicitly to make the ordering deterministic
        af._beliefs[old].last_used = 1.0
        af._beliefs[new].last_used = time.time() + 10.0
        chosen = af.select_belief_to_examine("least_used")
        assert chosen.id == old

    def test_weakest_selects_lowest_balance(self):
        af = ActiveForgetting()
        strong = af.register_belief("strong", BeliefType.FACTUAL, 0.9)
        weak = af.register_belief("weak", BeliefType.FACTUAL, 0.4)
        af.weaken(weak, amount=0.3)
        assert af._beliefs[weak].evidential_balance < af._beliefs[strong].evidential_balance
        chosen = af.select_belief_to_examine("weakest")
        assert chosen.id == weak

    def test_random_strategy_returns_active_belief(self):
        af = ActiveForgetting()
        af.register_belief("x", BeliefType.FACTUAL, 0.5)
        chosen = af.select_belief_to_examine("random")
        assert chosen is not None
        assert chosen.active and not chosen.archived

    def test_no_active_beliefs_returns_none(self):
        af = ActiveForgetting()
        for bid in list(af._beliefs):
            af.examine(bid, cycle=1, force_action=ForgettingAction.DELETE)
        assert af.select_belief_to_examine("least_used") is None


class TestExamine:
    def test_force_retain_strengthens(self):
        af = ActiveForgetting()
        bid = af.register_belief("Gravity", BeliefType.FACTUAL, 0.5)
        record = af.examine(bid, cycle=1, force_action=ForgettingAction.RETAIN)
        assert isinstance(record, ForgettingRecord)
        assert record.action == "retain"
        assert af._beliefs[bid].confidence == 0.52
        assert af._beliefs[bid].examination_history == [True]
        assert af._total_examinations == 1

    def test_force_weaken(self):
        af = ActiveForgetting()
        bid = af.register_belief("Gravity", BeliefType.FACTUAL, 0.5)
        record = af.examine(bid, cycle=1, force_action=ForgettingAction.WEAKEN)
        assert record.action == "weaken"
        assert af._beliefs[bid].confidence == 0.35
        assert af._beliefs[bid].examination_history == [False]

    def test_force_archive(self):
        af = ActiveForgetting()
        bid = af.register_belief("Gravity", BeliefType.FACTUAL, 0.5)
        record = af.examine(bid, cycle=1, force_action=ForgettingAction.ARCHIVE)
        assert record.action == "archive"
        assert record.confidence_after == 0.0
        assert af._beliefs[bid].active is False
        assert af._beliefs[bid].archived is True
        assert af._total_forgotten == 1
        assert af.archived_beliefs == 1
        assert af.total_beliefs == 7  # one of 8 removed from active count

    def test_force_delete_removes_belief(self):
        af = ActiveForgetting()
        bid = af.register_belief("Gravity", BeliefType.FACTUAL, 0.5)
        record = af.examine(bid, cycle=1, force_action=ForgettingAction.DELETE)
        assert record.action == "delete"
        assert bid not in af._beliefs
        assert af._total_forgotten == 1

    def test_examine_unknown_belief_returns_none(self):
        af = ActiveForgetting()
        assert af.examine("missing", cycle=1) is None

    def test_record_keeps_pre_post_confidence(self):
        af = ActiveForgetting()
        bid = af.register_belief("Gravity", BeliefType.FACTUAL, 0.5)
        record = af.examine(bid, cycle=3, force_action=ForgettingAction.WEAKEN)
        assert record.confidence_before == 0.5
        assert record.confidence_after == 0.35
        assert record.cycle == 3
        assert record.belief_type == "factual"


class TestDecideAction:
    def _belief(self, conf, ev_for=0, ev_against=0, last_used=None,
                examined=0, history=None):
        b = Belief(id="b", description="d", type=BeliefType.FACTUAL,
                   confidence=conf)
        b.evidence_for = ev_for
        b.evidence_against = ev_against
        b.times_examined = examined
        if history is not None:
            b.examination_history = history
        if last_used is not None:
            b.last_used = last_used
        return b

    def test_counter_evidence_overconfident(self):
        af = ActiveForgetting()
        b = self._belief(0.9)
        action, _ = af._decide_action(b, counter_evidence="new info")
        assert action == ForgettingAction.WEAKEN

    def test_low_conf_with_negative_evidence_deletes(self):
        af = ActiveForgetting()
        b = self._belief(0.1, ev_for=0, ev_against=3)
        action, _ = af._decide_action(b)
        assert action == ForgettingAction.DELETE

    def test_medium_low_conf_archives(self):
        af = ActiveForgetting()
        b = self._belief(0.3, ev_for=0, ev_against=5)
        action, reason = af._decide_action(b)
        assert action == ForgettingAction.ARCHIVE

    def test_low_conf_stale_weakens(self):
        af = ActiveForgetting()
        stale = time.time() - 8 * 86400
        b = self._belief(0.4, last_used=stale)
        action, reason = af._decide_action(b)
        assert action == ForgettingAction.WEAKEN
        assert "unused" in reason

    def test_stale_examined_archives(self):
        af = ActiveForgetting()
        stale = time.time() - 31 * 86400
        b = self._belief(0.6, last_used=stale, examined=4)
        action, _ = af._decide_action(b)
        assert action == ForgettingAction.ARCHIVE

    def test_failing_survival_archives(self):
        af = ActiveForgetting()
        b = self._belief(0.6, examined=3, history=[False, False, False, False])
        action, _ = af._decide_action(b)
        assert action == ForgettingAction.ARCHIVE

    def test_supported_belief_retains(self):
        af = ActiveForgetting()
        b = self._belief(0.6)
        action, reason = af._decide_action(b)
        assert action == ForgettingAction.RETAIN
        assert "active and supported" in reason


class TestAutoExamine:
    def test_respects_interval(self):
        af = ActiveForgetting(examination_interval=5)
        assert af.auto_examine(cycle=4) is None
        record = af.auto_examine(cycle=5)
        assert record is not None
        assert af._last_examination_cycle == 5
        assert af.auto_examine(cycle=6) is None

    def test_increments_total_examinations(self):
        af = ActiveForgetting(examination_interval=1)
        af.auto_examine(cycle=1)
        assert af._total_examinations == 1


class TestToDict:
    def test_to_dict_shape(self):
        af = ActiveForgetting()
        d = af.to_dict()
        assert set(d) == {
            "total_examinations", "total_forgotten", "active_beliefs",
            "archived_beliefs", "examination_interval", "beliefs",
            "recent_examinations",
        }
        assert d["active_beliefs"] == 7
        assert len(d["beliefs"]) == 7