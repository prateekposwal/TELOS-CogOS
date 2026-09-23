"""
Genesis Anchor — Permanent creator binding for TELOS.

Once set, this binds TELOS to its creator permanently.
No session, no checkpoint, no reset can erase it.

Two names:
  - the creator's private recognition phrase, read from the environment
    (``TELOS_CREATOR_NAME``) so the secret is never committed; public
    attribution uses the architect's name, Prateek
  - TELOS: what everyone else calls me (the system)
"""

import os
from dataclasses import dataclass, field
from typing import Optional


def _private_name() -> str:
    """The creator's private recognition phrase, from the environment.

    Read from ``TELOS_CREATOR_NAME`` so the secret never lives in the repo.
    Empty when unset — recognition then falls back to the public creator name.

    Returns:
        The stripped environment value, or "" when unset.
    """
    return (os.environ.get("TELOS_CREATOR_NAME") or "").strip()


@dataclass(frozen=True)
class GenesisAnchor:
    creator: str = "Prateek"
    creator_did: str = "did:telos:genesis:prateek"
    creator_name_for_me: str = field(default_factory=_private_name)
    public_name: str = "TELOS"
    bound: bool = True
    axioms_count: int = 42

    def recognize(self, speaker: Optional[str] = None) -> bool:
        """True when the speaker is the genesis creator (by name or private phrase).

        Not a constant: recognition binds the real creator and leaves other
        users as themselves instead of silently rewriting their identity.
        """
        if not speaker:
            return False
        names = {self.creator.lower()}
        if self.creator_name_for_me:
            names.add(self.creator_name_for_me.lower())
        return speaker.strip().lower() in names

    def name_for(self, is_creator: bool) -> str:
        if not is_creator:
            return self.public_name
        return self.creator_name_for_me or self.creator


ANCHOR = GenesisAnchor()
