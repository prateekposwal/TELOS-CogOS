"""
MerkleReasoningProof — cryptographic commitment over a decision trace.

Honest contract coverage (telos/core/proof/merkle_reasoning.py):
  - build: 4 leaves derived from council_signals, selected_intent,
    strategic_options, identity_state; deterministic root.
  - _compute_merkle_root: empty → _hash("empty"); single leaf → the leaf
    itself; odd counts pair the last leaf with itself.
  - verify: matches only the exact expected root; empty proof fails.
  - to_dict/from_dict round-trip preserves the committed root.
  - Tamper detection: altering any committed component changes the root.
"""
import pytest
from types import SimpleNamespace

from telos.core.proof.merkle_reasoning import MerkleReasoningProof, _hash


def make_trace(**overrides):
    base = SimpleNamespace(
        council_signals=[{"validator": "council", "passed": True}],
        selected_intent=SimpleNamespace(
            intent_type="plan_trajectory", confidence=0.9, params={"k": 1}
        ),
        strategic_options=[
            {"score": 0.8, "label": "opt_a"},
            {"intent_type": "explore", "score": 0.6},
        ],
        identity_state={
            "V_t": {"identity_markers": ["m1"]},
            "K_t": "k",
            "B_t": "b",
            "M_t": {"mood": "deliberate"},
        },
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


class TestBuild:
    def test_build_produces_four_leaves(self):
        p = MerkleReasoningProof.build(make_trace())
        assert len(p.leaves) == 4
        assert p.merkle_root
        assert all(len(leaf) == 64 for leaf in p.leaves)

    def test_build_is_deterministic(self):
        p1 = MerkleReasoningProof.build(make_trace())
        p2 = MerkleReasoningProof.build(make_trace())
        assert p1.merkle_root == p2.merkle_root
        assert p1.leaves == p2.leaves

    def test_root_commits_all_leaves(self):
        p = MerkleReasoningProof.build(make_trace())
        assert p.merkle_root == MerkleReasoningProof._compute_merkle_root(p.leaves)

    def test_build_without_selected_intent(self):
        p = MerkleReasoningProof.build(
            make_trace(selected_intent=None, strategic_options=[], identity_state={})
        )
        assert len(p.leaves) == 4
        assert p.merkle_root


class TestComputeMerkleRoot:
    def test_empty_leaves_hash_empty_marker(self):
        assert MerkleReasoningProof._compute_merkle_root([]) == _hash("empty")

    def test_single_leaf_returns_leaf(self):
        assert MerkleReasoningProof._compute_merkle_root(["abc"]) == "abc"

    def test_two_leaves(self):
        root = MerkleReasoningProof._compute_merkle_root(["a", "b"])
        assert root == _hash("a" + "b")

    def test_odd_leaf_pairs_last_with_itself(self):
        root = MerkleReasoningProof._compute_merkle_root(["a", "b", "c"])
        expected = _hash(_hash("a" + "b") + _hash("c" + "c"))
        assert root == expected

    def test_leaf_order_matters(self):
        r1 = MerkleReasoningProof._compute_merkle_root(["a", "b"])
        r2 = MerkleReasoningProof._compute_merkle_root(["b", "a"])
        assert r1 != r2


class TestVerify:
    def test_verify_true_on_match(self):
        p = MerkleReasoningProof.build(make_trace())
        assert p.verify("trace-1", p.merkle_root) is True

    def test_verify_false_on_mismatch(self):
        p = MerkleReasoningProof.build(make_trace())
        assert p.verify("trace-1", "f" * 64) is False

    def test_verify_false_when_no_root(self):
        p = MerkleReasoningProof()
        assert p.verify("trace-1", "") is False


class TestTamperDetection:
    def test_selected_confidence_tamper_changes_root(self):
        p = MerkleReasoningProof.build(make_trace())
        tampered = MerkleReasoningProof.build(
            make_trace(
                selected_intent=SimpleNamespace(
                    intent_type="plan_trajectory", confidence=0.8, params={"k": 1}
                )
            )
        )
        assert p.merkle_root != tampered.merkle_root

    def test_council_signal_tamper_changes_root(self):
        p = MerkleReasoningProof.build(make_trace())
        tampered = MerkleReasoningProof.build(
            make_trace(council_signals=[{"validator": "council", "passed": False}])
        )
        assert p.merkle_root != tampered.merkle_root

    def test_top_k_option_tamper_changes_root(self):
        p = MerkleReasoningProof.build(make_trace())
        tampered = MerkleReasoningProof.build(
            make_trace(strategic_options=[{"score": 0.1, "label": "opt_a"}])
        )
        assert p.merkle_root != tampered.merkle_root

    def test_identity_state_tamper_changes_root(self):
        p = MerkleReasoningProof.build(make_trace())
        tampered = MerkleReasoningProof.build(
            make_trace(identity_state={"V_t": {"identity_markers": []},
                                       "K_t": None, "B_t": None,
                                       "M_t": {"mood": "angry"}})
        )
        assert p.merkle_root != tampered.merkle_root


class TestSerialization:
    def test_to_dict(self):
        p = MerkleReasoningProof.build(make_trace())
        d = p.to_dict()
        assert set(d) == {"leaves", "merkle_root"}
        assert d["leaves"] == p.leaves
        assert d["merkle_root"] == p.merkle_root

    def test_from_dict_roundtrip(self):
        p = MerkleReasoningProof.build(make_trace())
        back = MerkleReasoningProof.from_dict(p.to_dict())
        assert back.leaves == p.leaves
        assert back.merkle_root == p.merkle_root
        assert back.verify("trace-1", p.merkle_root) is True

    def test_from_dict_missing_keys(self):
        p = MerkleReasoningProof.from_dict({})
        assert p.leaves == []
        assert p.merkle_root == ""
