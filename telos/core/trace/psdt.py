"""Partially Signed Decision Trace — standard format for cross-stream reasoning handoffs.

Each stream signs its analysis (intent, confidence, evidence) before passing to the next.
The full trace is assembled from partial signatures, making the pipeline auditable
independently at each phase.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import hashlib
import json


@dataclass
class PartialDecision:
    """A single stream's contribution to the final decision."""
    stream_name: str
    stream_priority: float
    intent_type: str
    confidence: float
    evidence_hash: str  # hash of the evidence this stream considered
    signature: str = ""  # sha256(stream_name + intent_type + confidence + evidence_hash)

    def sign(self):
        content = f"{self.stream_name}:{self.intent_type}:{self.confidence}:{self.evidence_hash}"
        self.signature = hashlib.sha256(content.encode()).hexdigest()[:16]
        return self.signature

    def verify(self) -> bool:
        content = f"{self.stream_name}:{self.intent_type}:{self.confidence}:{self.evidence_hash}"
        expected = hashlib.sha256(content.encode()).hexdigest()[:16]
        return self.signature == expected


@dataclass
class PSDT:
    """Assembled from partial decisions across all streams."""
    partials: Dict[str, PartialDecision] = field(default_factory=dict)
    council_signature: str = ""

    def add_partial(self, partial: PartialDecision):
        partial.sign()
        self.partials[partial.stream_name] = partial

    def finalize(self, council_verdict: str):
        """Council signs the full assembly.
            Args:
                council_verdict: the council_verdict argument for this call.
        """
        content = json.dumps({k: v.signature for k, v in self.partials.items()}, sort_keys=True)
        self.council_signature = hashlib.sha256((content + council_verdict).encode()).hexdigest()[:16]

    def verify_full(self) -> bool:
        """Verify all partials + council signature."""
        for p in self.partials.values():
            if not p.verify():
                return False
        return bool(self.council_signature)

    def to_dict(self) -> Dict:
        return {
            "partials": {k: {"intent": v.intent_type, "confidence": v.confidence, "signature": v.signature} for k, v in self.partials.items()},
            "council_signature": self.council_signature,
        }

    @classmethod
    def from_ctx(cls, ctx) -> 'PSDT':
        """Extract PSDT from PhaseContext, or return empty if not present.
            Args:
                ctx: the phase context for this cycle
        """
        stored = getattr(ctx, 'psdt', None)
        if isinstance(stored, cls):
            return stored
        return cls()
