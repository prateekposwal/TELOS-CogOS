"""
DecisionMempool — Pool of pending intents/options waiting for council approval.

Bitcoin-inspired: Like a transaction mempool, intents are submitted before
council validation, held pending, then confirmed or rejected by the council.
This provides a visible queue of decisions-in-flight and prevents intents
from being acted on without going through the full validation process.
"""

import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('telos_mempool')


class MempoolStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


@dataclass
class MempoolEntry:
    """A single decision waiting for council validation."""
    intent_id: str
    intent_type: str
    confidence: float
    stream_name: str
    timestamp: float
    status: MempoolStatus = MempoolStatus.PENDING
    rejection_reason: Optional[str] = None
    priority: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)


class DecisionMempool:
    """Pool of pending intents/options waiting for council approval.

    Intents are submitted before council validation, held in pending state,
    then confirmed or rejected by the council. Provides full visibility
    into decisions-in-flight.

    Config:
        max_pending: Maximum number of pending entries (default: 100)
    """

    def __init__(self, max_pending: int = 100):
        self._pending: List[MempoolEntry] = []
        self._confirmed: List[MempoolEntry] = []
        self._rejected: List[MempoolEntry] = []
        self._max_pending = max_pending

    def submit(self, intent: Any, stream_name: str = "unknown",
               timestamp: Optional[float] = None) -> str:
        """Submit an intent for council review.

        Args:
            intent: IntentIR object with intent_type, confidence, etc.
            stream_name: Name of the stream that produced this intent.
            timestamp: When the intent was produced (default: now).

        Returns:
            intent_id string for tracking.
        """
        intent_id = f"intent_{int(timestamp or time.time())}_{len(self._pending)}"
        entry = MempoolEntry(
            intent_id=intent_id,
            intent_type=getattr(intent, 'intent_type', str(intent)),
            confidence=getattr(intent, 'confidence', 0.0),
            stream_name=stream_name,
            timestamp=timestamp or time.time(),
            priority=getattr(intent, 'priority', 0.5),
            status=MempoolStatus.PENDING,
        )
        self._pending.append(entry)

        # Enforce capacity limit
        if len(self._pending) > self._max_pending:
            # Remove oldest pending
            removed = self._pending.pop(0)
            logger.debug(f"Mempool: dropped oldest pending {removed.intent_id}")

        logger.debug(f"Mempool: submitted {intent_id} ({entry.intent_type}, conf={entry.confidence:.2f})")
        return intent_id

    def confirm(self, intent_id: str) -> bool:
        """Council approved — move from pending to confirmed.

        Args:
            intent_id: The intent_id to confirm.

        Returns:
            True if found and confirmed, False if not found.
        """
        for i, entry in enumerate(self._pending):
            if entry.intent_id == intent_id:
                entry.status = MempoolStatus.CONFIRMED
                self._confirmed.append(entry)
                self._pending.pop(i)
                logger.debug(f"Mempool: confirmed {intent_id}")
                return True
        logger.warning(f"Mempool: cannot confirm unknown intent {intent_id}")
        return False

    def reject(self, intent_id: str, reason: str = "") -> bool:
        """Council rejected — log and discard.

        Args:
            intent_id: The intent_id to reject.
            reason: Why it was rejected.

        Returns:
            True if found and rejected, False if not found.
        """
        for i, entry in enumerate(self._pending):
            if entry.intent_id == intent_id:
                entry.status = MempoolStatus.REJECTED
                entry.rejection_reason = reason
                self._rejected.append(entry)
                self._pending.pop(i)
                logger.debug(f"Mempool: rejected {intent_id} ({reason})")
                return True
        return False

    def get_pending(self) -> List[MempoolEntry]:
        """Get all pending decisions visible before commitment."""
        return list(self._pending)

    def get_confirmed(self) -> List[MempoolEntry]:
        """Get all confirmed decisions."""
        return list(self._confirmed)

    def get_rejected(self) -> List[MempoolEntry]:
        """Get all rejected decisions with reasons."""
        return list(self._rejected)

    def clear(self) -> None:
        """Clear all entries (for testing or session reset)."""
        self._pending.clear()
        self._confirmed.clear()
        self._rejected.clear()

    @property
    def mempool_full(self) -> bool:
        """Check if the mempool is at capacity."""
        return len(self._pending) >= self._max_pending

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def stats(self) -> Dict:
        return {
            "pending": len(self._pending),
            "confirmed": len(self._confirmed),
            "rejected": len(self._rejected),
            "mempool_full": self.mempool_full,
            "max_pending": self._max_pending,
        }
