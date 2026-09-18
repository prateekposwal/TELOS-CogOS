"""
TieredContext — Three-Tier Context Compression for Session Continuity.

Three tiers eliminate the need for "start fresh" by managing conversation
context in layers:

  TIER 1 — HOT (last N turns, default 10): Full fidelity.
  TIER 2 — WARM (beyond HOT, up to limit):   Compressed per-turn summaries.
  TIER 3 — COLD (everything older):           One-paragraph narrative + key facts.

Flow:
  add_message(msg)
    → HOT tier capped at hot_limit
    → if HOT overflows: pop oldest 2, compress to 1 sentence, push to WARM
    → WARM tier capped at warm_limit
    → if WARM overflows: pop oldest 5, summarize to paragraph + essence, push to COLD
    → COLD tier: { paragraph, essence, timestamp }

Axioms: 1.2 (Process over Outcomes), 2.2 (Feedback Loops), 4.7 (System Memory)
"""

from __future__ import annotations

import json
import time
import logging
from typing import Dict, List, Optional, Any, Callable, Tuple

from telos.core.attention.token_budget import estimate_tokens, estimate_message_tokens
from telos.core.context.summarizer import ContextSummarizer, SessionEssence

logger = logging.getLogger('telos_tiered_context')

DEFAULT_HOT_LIMIT = 10
DEFAULT_WARM_LIMIT = 20
DEFAULT_COLD_COMPRESS_COUNT = 5
DEFAULT_TOKEN_BUDGET = 4096


class TieredContext:
    """Three-tier context compression for infinite session continuity.

    Usage:
        tc = TieredContext(hot_limit=10, warm_limit=20)
        tc.add_message({"role": "user", "content": "Hello"})
        tc.add_message({"role": "assistant", "content": "Hi there"})
        context = tc.get_context()  # combined view across all tiers
        pressure = tc.get_pressure()  # 0.0–1.0

    Serialization:
        data = tc.to_dict()
        tc2 = TieredContext.from_dict(data)
    """

    def __init__(self,
                 hot_limit: int = DEFAULT_HOT_LIMIT,
                 warm_limit: int = DEFAULT_WARM_LIMIT,
                 cold_compress_count: int = DEFAULT_COLD_COMPRESS_COUNT,
                 token_budget: int = DEFAULT_TOKEN_BUDGET,
                 summarizer: Optional[ContextSummarizer] = None,
                 ollama_chat_fn: Optional[Callable] = None):
        self.hot_limit = max(2, hot_limit)
        self.warm_limit = max(2, warm_limit)
        self.cold_compress_count = max(1, cold_compress_count)
        self.token_budget = max(256, token_budget)

        # — Three Tiers —
        self.hot: List[Dict] = []          # Raw message dicts
        self.warm: List[Dict] = []         # Compressed per-turn summaries
        self.cold: Optional[Dict] = None   # {paragraph, essence, timestamp, source_count}

        # Summarizer for COLD-tier LLM calls (optional)
        if summarizer:
            self._summarizer = summarizer
        elif ollama_chat_fn:
            self._summarizer = ContextSummarizer(ollama_chat_fn=ollama_chat_fn)
        else:
            self._summarizer = None

        # Running total of messages ever added
        self._total_messages_added: int = 0

    # ── Public API ─────────────────────────────────────────────────────

    def add_message(self, msg: Dict,
                    trace_signal: Optional[float] = None) -> None:
        """Add a message to the HOT tier.

        If HOT exceeds hot_limit, oldest messages are compressed and
        promoted to WARM. If WARM exceeds warm_limit, oldest WARM entries
        are summarized and promoted to COLD.

        Args:
            msg: Message dict with 'role' and 'content' keys.
            trace_signal: Optional signal score (0.0–1.0) for prioritization.
                          Higher signal = more likely to be preserved.
        """
        msg = dict(msg)  # shallow copy
        if trace_signal is not None:
            msg['_trace_signal'] = max(0.0, min(1.0, trace_signal))

        self.hot.append(msg)
        self._total_messages_added += 1
        self._maybe_compress()

    def get_context(self) -> List[Dict]:
        """Return combined context across all three tiers.

        Returns:
            List of message dicts: HOT messages (full fidelity) followed by
            WARM summary block and COLD essence block as synthetic system messages.
        """
        result: List[Dict] = list(self.hot)  # deep enough; dicts are copied by list()

        if self.warm:
            warm_lines = []
            for i, entry in enumerate(self.warm):
                content = entry.get('content', '')
                if content:
                    warm_lines.append(f"[WARM {i}] {content}")
            if warm_lines:
                result.append({
                    "role": "system",
                    "content": "=== COMPRESSED HISTORY (TIER 2 — WARM) ===\n"
                               + "\n".join(warm_lines),
                })

        if self.cold:
            para = self.cold.get('paragraph', '')
            essence = self.cold.get('essence', {})
            block = "=== SESSION ESSENCE (TIER 3 — COLD) ===\n"
            if para:
                block += para + "\n\n"
            if essence:
                block += f"Key Decisions: {json.dumps(essence.get('key_decisions', []))}\n"
                block += f"User Preferences: {json.dumps(essence.get('user_preferences', []))}\n"
                block += f"Recurring Intents: {json.dumps(essence.get('recurring_intents', []))}\n"
                block += f"Mood Trajectory: {essence.get('mood_trajectory', 'neutral')}\n"
                block += f"Blockers Resolved: {json.dumps(essence.get('blockers_resolved', []))}\n"
            result.append({"role": "system", "content": block.strip()})

        return result

    def get_token_estimate(self) -> int:
        """Estimate total token usage across all three tiers.

        Uses the same heuristic as TokenBudgetManager
        (chars_per_token ~= 4.0).
        """
        total = 0

        # HOT tier: full messages
        for msg in self.hot:
            total += estimate_message_tokens(msg)

        # WARM tier: compressed summaries (shorter but still count)
        for entry in self.warm:
            total += estimate_message_tokens(entry)

        # COLD tier: paragraph + essence
        if self.cold:
            para = self.cold.get('paragraph', '')
            essence = self.cold.get('essence', {})
            cold_text = para + json.dumps(essence)
            total += estimate_tokens(cold_text) + 20  # overhead

        return total

    def get_pressure(self) -> float:
        """Return context pressure as a float in [0.0, 1.0].

        0.0 = no pressure (empty context)
        1.0 = at or over token budget
        """
        tokens = self.get_token_estimate()
        if self.token_budget <= 0:
            return 1.0
        return min(1.0, tokens / self.token_budget)

    def compress(self) -> None:
        """Force full compression: HOT → WARM → COLD.

        Moves all messages out of HOT (into WARM), then compresses WARM
        into COLD until all tiers are within limits. After this call,
        HOT will be empty (or minimal) and all context is in WARM/COLD.
        """
        # Drain HOT into WARM (pairwise compression)
        while len(self.hot) >= 2:
            pair = [self.hot.pop(0), self.hot.pop(0)]
            summary = self._compress_pair_to_sentence(pair)
            self.warm.append(summary)

        # If one orphan left in HOT, compress it solo
        if self.hot:
            solo = [self.hot.pop(0)]
            summary = self._compress_pair_to_sentence(solo)
            self.warm.append(summary)

        # Drain WARM into COLD
        while len(self.warm) > 0:
            batch = []
            for _ in range(min(self.cold_compress_count, len(self.warm))):
                batch.append(self.warm.pop(0))
            cold_block = self._summarize_warm_to_cold(batch)
            self._merge_cold(cold_block)

    def to_dict(self) -> Dict:
        """Serialize the full TieredContext state for checkpointing."""
        warm_data = []
        for entry in self.warm:
            warm_data.append({
                'role': entry.get('role', 'system'),
                'content': entry.get('content', ''),
            })

        return {
            'version': 1,
            'hot': list(self.hot),
            'warm': warm_data,
            'cold': dict(self.cold) if self.cold else None,
            'config': {
                'hot_limit': self.hot_limit,
                'warm_limit': self.warm_limit,
                'cold_compress_count': self.cold_compress_count,
                'token_budget': self.token_budget,
            },
            '_total_messages_added': self._total_messages_added,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'TieredContext':
        """Deserialize a TieredContext from a dict produced by to_dict().
            Args:
                data: the data to process
        """
        config = data.get('config', {})
        tc = cls(
            hot_limit=config.get('hot_limit', DEFAULT_HOT_LIMIT),
            warm_limit=config.get('warm_limit', DEFAULT_WARM_LIMIT),
            cold_compress_count=config.get('cold_compress_count', DEFAULT_COLD_COMPRESS_COUNT),
            token_budget=config.get('token_budget', DEFAULT_TOKEN_BUDGET),
        )
        tc.hot = list(data.get('hot', []))
        tc.warm = list(data.get('warm', []))
        tc.cold = dict(data['cold']) if data.get('cold') else None
        tc._total_messages_added = data.get('_total_messages_added', 0)
        return tc

    @classmethod
    def from_chat_history(cls,
                          chat_history: List[Dict],
                          **kwargs) -> 'TieredContext':
        """Build a TieredContext from an existing chat_history list.

        All messages are loaded into HOT (then compression runs automatically
        to distribute them across tiers).
        """
        tc = cls(**kwargs)
        for msg in chat_history:
            tc.add_message(msg)
        return tc

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def size(self) -> Dict[str, int]:
        """Return current size of each tier."""
        return {
            'hot': len(self.hot),
            'warm': len(self.warm),
            'cold': 1 if self.cold else 0,
            'total_messages': self._total_messages_added,
        }

    # ── Internal Compression Logic ─────────────────────────────────────

    def _maybe_compress(self) -> None:
        """Check tier limits and compress if needed."""
        # HOT → WARM: pop oldest 2, compress to 1 sentence
        while len(self.hot) > self.hot_limit and len(self.hot) >= 2:
            pair = [self.hot.pop(0), self.hot.pop(0)]
            summary = self._compress_pair_to_sentence(pair)
            self.warm.append(summary)
            logger.debug(
                f"TieredContext: HOT → WARM — compressed pair "
                f"({pair[0].get('role','?')}+{pair[1].get('role','?')}) → 1 sentence"
            )

        # WARM → COLD: pop oldest N, summarize to paragraph + essence
        while len(self.warm) > self.warm_limit and len(self.warm) >= self.cold_compress_count:
            batch = []
            for _ in range(self.cold_compress_count):
                batch.append(self.warm.pop(0))
            cold_block = self._summarize_warm_to_cold(batch)
            self._merge_cold(cold_block)
            logger.debug(
                f"TieredContext: WARM → COLD — compressed {len(batch)} summaries "
                f"→ cold block"
            )

    def _compress_pair_to_sentence(self, pair: List[Dict]) -> Dict:
        """Compress a pair (or single) of messages into a 1-sentence summary.

        Uses algorithmic extraction (no LLM call).

        Args:
            pair: 1 or 2 message dicts.

        Returns:
            A summary dict with role='system' and compressed content.
        """
        parts = []
        for msg in pair:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            # Truncate very long content and extract first line
            short = content.strip().split('\n')[0] if content else ''
            if len(short) > 120:
                short = short[:120] + '…'
            if short:
                parts.append(f"[{role}] {short}")

        summary_text = ' | '.join(parts) if parts else '(empty exchange)'

        return {
            'role': 'system',
            'content': summary_text,
            '_compressed': True,
            '_timestamp': time.time(),
        }

    def _summarize_warm_to_cold(self,
                                 batch: List[Dict]) -> Dict:
        """Compress a batch of WARM entries into a COLD block.

        Tries to use ContextSummarizer if available; falls back to
        algorithmic concatenation + simple essence extraction.

        Args:
            batch: List of WARM summary dicts.

        Returns:
            Cold block dict: {paragraph, essence, timestamp, source_count}
        """
        # Build the batch text for summarization
        batch_text = '\n'.join(
            f"[{e.get('role', 'system')}] {e.get('content', '')}"
            for e in batch
        )

        # Try LLM-based summarization if available
        if self._summarizer is not None:
            try:
                chat_history_for_llm = [
                    {"role": "system", "content": f"Previous session summary batch:\n{batch_text}"}
                ]
                essence = self._summarizer._generate_summary(chat_history_for_llm)
                if essence is not None:
                    return {
                        'paragraph': self._build_paragraph_from_essence(essence, batch),
                        'essence': essence.to_dict(),
                        'timestamp': time.time(),
                        'source_count': len(batch),
                    }
            except Exception as e:
                logger.warning(f"TieredContext: LLM cold summary failed, using fallback: {e}")

        # Algorithmic fallback
        paragraph = batch_text.replace('\n', '; ')[:500]
        essence = SessionEssence(
            recurring_intents=self._extract_keywords(batch_text, max_items=5),
            mood_trajectory='neutral',
        )

        return {
            'paragraph': paragraph,
            'essence': essence.to_dict(),
            'timestamp': time.time(),
            'source_count': len(batch),
        }

    def _merge_cold(self, new_cold: Dict) -> None:
        """Merge a new cold block into the existing one (or store it).
            Args:
                new_cold: the new_cold argument for this call.
        """
        if self.cold is None:
            self.cold = new_cold
            return

        # Merge essences
        old_essence = SessionEssence.from_dict(self.cold.get('essence', {}))
        new_essence = SessionEssence.from_dict(new_cold.get('essence', {}))
        merged = old_essence.merge(new_essence)

        # Combine paragraphs
        old_para = self.cold.get('paragraph', '')
        new_para = new_cold.get('paragraph', '')
        combined = old_para
        if old_para and new_para:
            combined = old_para.rstrip('.') + '. ' + new_para
        elif new_para:
            combined = new_para

        self.cold = {
            'paragraph': combined,
            'essence': merged.to_dict(),
            'timestamp': time.time(),
            'source_count': (self.cold.get('source_count', 0)
                             + new_cold.get('source_count', 0)),
        }

    # ── Helper Utilities ───────────────────────────────────────────────

    @staticmethod
    def _build_paragraph_from_essence(essence: SessionEssence,
                                       batch: List[Dict]) -> str:
        """Build a narrative paragraph from a SessionEssence and source batch."""
        parts = []
        if essence.key_decisions:
            parts.append(f"Key decisions included: {'; '.join(essence.key_decisions[:3])}.")
        if essence.recurring_intents:
            parts.append(f"The user was focused on: {'; '.join(essence.recurring_intents[:3])}.")
        if essence.blockers_resolved:
            parts.append(f"Blockers resolved: {'; '.join(essence.blockers_resolved[:3])}.")
        parts.append(f"The tone was {essence.mood_trajectory}.")
        return ' '.join(parts)

    @staticmethod
    def _extract_keywords(text: str, max_items: int = 5) -> List[str]:
        """Simple keyword extraction from text for essence fallback.
            Args:
                max_items: the max_items argument for this call.
        """
        # Very simple: find words that appear frequently
        import re
        words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
        freq: Dict[str, int] = {}
        for w in words:
            if w not in ('this', 'that', 'with', 'from', 'have', 'been',
                         'were', 'what', 'when', 'where', 'which',
                         'their', 'there', 'about', 'would', 'could'):
                freq[w] = freq.get(w, 0) + 1
        sorted_words = sorted(freq.items(), key=lambda x: -x[1])
        return [w for w, c in sorted_words[:max_items]]
