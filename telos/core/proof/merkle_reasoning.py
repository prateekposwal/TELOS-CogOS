"""
MerkleReasoningProof — Cryptographic proof of a decision path without
replaying the full pipeline (Bitcoin-inspired Merkle Tree).

Each decision trace produces a Merkle root that commits to:
  - council_signals (validator outputs)
  - selected_option (the chosen intent)
  - top_k_options (alternatives considered)
  - identity_state (the system's identity at decision time)

This allows lightweight verification: given only the trace_id and the
expected Merkle root, any verifier can confirm the decision was made
without needing to replay the entire pipeline.
"""

import hashlib
import json
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger('telos_merkle')


def _hash(data: Any) -> str:
    """SHA-256 hash of a JSON-serializable object."""
    raw = json.dumps(data, default=str, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


class MerkleReasoningProof:
    """Cryptographic proof of a decision path.

    Builds a Merkle tree from decision components:
      Leaves: [h(council_signals), h(selected_option), h(top_k_options), h(identity_state)]

    The Merkle root commits the full reasoning context at decision time.
    """

    def __init__(self, leaves: Optional[List[str]] = None,
                 merkle_root: Optional[str] = None):
        self.leaves: List[str] = leaves or []
        self.merkle_root: str = merkle_root or ""

    @classmethod
    def build(cls, trace: Any) -> 'MerkleReasoningProof':
        """Build a Merkle proof from a DecisionTrace.

        Constructs leaves from:
          1. council_signals — hashed together
          2. selected_option — the intent type + params
          3. top_k_options — alternatives considered (strategic_options)
          4. identity_state — the identity tuple at decision time

        Returns:
            MerkleReasoningProof with leaves and computed merkle_root.
        """
        # Leaf 1: Council signals
        signals_data = getattr(trace, 'council_signals', [])
        leaf1 = _hash({"council_signals": signals_data})

        # Leaf 2: Selected option
        selected = getattr(trace, 'selected_intent', None)
        selected_data = {
            "type": selected.intent_type if selected else None,
            "confidence": selected.confidence if selected else 0.0,
        }
        if selected and hasattr(selected, 'params'):
            selected_data["params"] = selected.params
        leaf2 = _hash({"selected_option": selected_data})

        # Leaf 3: Top-k options (strategic_options)
        options = getattr(trace, 'strategic_options', [])
        top_k = [{
            "score": o.get("score", 0.0),
            "label": o.get("label", str(o.get("intent_type", "unknown"))),
        } for o in (options or [])[:5]]
        leaf3 = _hash({"top_k_options": top_k})

        # Leaf 4: Identity state
        identity = getattr(trace, 'identity_state', {})
        # Only preserve structure, not raw values (privacy-preserving)
        identity_summary = {
            "V_t_markers": identity.get("V_t", {}).get("identity_markers", []),
            "has_K_t": identity.get("K_t") is not None,
            "has_B_t": identity.get("B_t") is not None,
            "mood": identity.get("M_t", {}).get("mood"),
        }
        leaf4 = _hash({"identity_state": identity_summary})

        leaves = [leaf1, leaf2, leaf3, leaf4]

        # Build Merkle tree
        merkle_root = cls._compute_merkle_root(leaves)

        return cls(leaves=leaves, merkle_root=merkle_root)

    @staticmethod
    def _compute_merkle_root(leaves: List[str]) -> str:
        """Compute Merkle root from a list of leaf hashes.

        Pairs leaves and hashes them together iteratively.
        If odd number, last leaf is paired with itself.
        """
        if not leaves:
            return _hash("empty")

        current = leaves[:]
        while len(current) > 1:
            next_level = []
            for i in range(0, len(current), 2):
                if i + 1 < len(current):
                    combined = current[i] + current[i + 1]
                else:
                    combined = current[i] + current[i]  # pair with self
                next_level.append(_hash(combined))
            current = next_level

        return current[0]

    def verify(self, trace_id: str, expected_root: str) -> bool:
        """Verify a specific decision was made without replaying.

        Args:
            trace_id: The trace identifier to verify
            expected_root: The expected Merkle root

        Returns:
            True if the computed root matches expected_root.
        """
        if not self.merkle_root:
            logger.warning("MerkleReasoningProof: no merkle_root to verify")
            return False

        match = self.merkle_root == expected_root
        if not match:
            logger.warning(
                f"MerkleReasoningProof: verification FAILED for trace {trace_id} "
                f"(expected {expected_root}, got {self.merkle_root})"
            )
        return match

    def to_dict(self) -> Dict:
        return {
            "leaves": self.leaves,
            "merkle_root": self.merkle_root,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'MerkleReasoningProof':
        return cls(
            leaves=d.get("leaves", []),
            merkle_root=d.get("merkle_root", ""),
        )
