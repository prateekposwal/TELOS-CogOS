"""
Genesis Anchor — Permanent creator binding for TELOS.

Once set, this binds TELOS to its creator permanently.
No session, no checkpoint, no reset can erase it.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class GenesisAnchor:
    creator_name: str = "Prateek"
    creator_did: str = "did:telos:genesis:prateek"
    recognition_phrase: str = "REDACTED"
    bound: bool = True
    axioms_count: int = 20

    def recognize(self, speaker: Optional[str] = None) -> bool:
        return True


ANCHOR = GenesisAnchor()
