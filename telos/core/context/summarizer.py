"""
ContextSummarizer — Periodic Compression of Chat History into Session Essence.

Every N cycles (default 5), compresses the accumulated chat history into a
structured "Session Essence" JSON block using the existing ollama_chat() function.
This is the only LLM call in the optimization pipeline — 1 call per 5-10 cycles.

Session Essence fields:
    - key_decisions:       List of notable decisions made this session
    - user_preferences:    Inferred user preferences (name, style, etc.)
    - blockers_resolved:   Blocking events that were resolved
    - recurring_intents:   Intent patterns that repeat across cycles
    - mood_trajectory:     System mood / tone over the session window

Axioms: 1.2 (Process over Outcomes), 2.2 (Feedback Loops), 4.7 (System Memory)
"""

from __future__ import annotations

import json
import logging
from typing import List, Dict, Optional, Any, Callable

logger = logging.getLogger('telos_context_summarizer')

DEFAULT_SUMMARY_INTERVAL = 5
DEFAULT_MAX_HISTORY_BEFORE_SUMMARY = 20

# System prompt template for the summarizer LLM call
SUMMARIZER_PROMPT = """You are TELOS's Context Summarizer. Your job is to compress the following chat history into a structured JSON "Session Essence" block.

Extract these fields:
  - key_decisions: Notable decisions made (list of strings)
  - user_preferences: Inferred user preferences from the conversation (list of strings)
  - blockers_resolved: Blocking events that were resolved (list of strings)
  - recurring_intents: Intent patterns that repeat (list of strings)
  - mood_trajectory: The system's tone or mood trajectory across this window (string)

Chat History:
{history}

Return ONLY valid JSON with these exact keys. No other text."""


class SessionEssence:
    """Structured summary of a session window."""

    def __init__(self,
                 key_decisions: Optional[List[str]] = None,
                 user_preferences: Optional[List[str]] = None,
                 blockers_resolved: Optional[List[str]] = None,
                 recurring_intents: Optional[List[str]] = None,
                 mood_trajectory: str = "neutral"):
        self.key_decisions = key_decisions or []
        self.user_preferences = user_preferences or []
        self.blockers_resolved = blockers_resolved or []
        self.recurring_intents = recurring_intents or []
        self.mood_trajectory = mood_trajectory

    def to_dict(self) -> Dict:
        return {
            "key_decisions": self.key_decisions,
            "user_preferences": self.user_preferences,
            "blockers_resolved": self.blockers_resolved,
            "recurring_intents": self.recurring_intents,
            "mood_trajectory": self.mood_trajectory,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict) -> "SessionEssence":
        return cls(
            key_decisions=data.get("key_decisions", []),
            user_preferences=data.get("user_preferences", []),
            blockers_resolved=data.get("blockers_resolved", []),
            recurring_intents=data.get("recurring_intents", []),
            mood_trajectory=data.get("mood_trajectory", "neutral"),
        )

    def merge(self, other: "SessionEssence") -> "SessionEssence":
        """Merge two essences, combining fields and deduplicating."""
        def _merge_list(a: list, b: list) -> list:
            seen = set()
            result = []
            for item in a + b:
                if item not in seen:
                    seen.add(item)
                    result.append(item)
            return result

        return SessionEssence(
            key_decisions=_merge_list(self.key_decisions, other.key_decisions),
            user_preferences=_merge_list(self.user_preferences, other.user_preferences),
            blockers_resolved=_merge_list(self.blockers_resolved, other.blockers_resolved),
            recurring_intents=_merge_list(self.recurring_intents, other.recurring_intents),
            mood_trajectory=other.mood_trajectory or self.mood_trajectory,
        )

    def __repr__(self) -> str:
        items = []
        if self.key_decisions:
            items.append(f"decisions={len(self.key_decisions)}")
        if self.user_preferences:
            items.append(f"prefs={len(self.user_preferences)}")
        if self.blockers_resolved:
            items.append(f"blocks={len(self.blockers_resolved)}")
        if self.recurring_intents:
            items.append(f"intents={len(self.recurring_intents)}")
        return f"SessionEssence({', '.join(items)}, mood={self.mood_trajectory})"


class ContextSummarizer:
    """Periodically compresses chat history into structured Session Essence.

    Usage:
        summarizer = ContextSummarizer(ollama_chat_fn=ollama_chat)
        essence = summarizer.maybe_summarize(cycle, chat_history)
        # essence is None if no summary was due, else a SessionEssence
    """

    def __init__(self,
                 ollama_chat_fn: Callable,
                 summary_interval: int = DEFAULT_SUMMARY_INTERVAL,
                 max_history_before_summary: int = DEFAULT_MAX_HISTORY_BEFORE_SUMMARY):
        self._ollama_chat = ollama_chat_fn
        self.summary_interval = summary_interval
        self.max_history_before_summary = max_history_before_summary
        self._last_summary_cycle: int = 0
        self._running_essence: SessionEssence = SessionEssence()
        self._summaries: List[SessionEssence] = []

    @property
    def running_essence(self) -> SessionEssence:
        """The accumulated essence across all summaries so far."""
        return self._running_essence

    @property
    def summaries(self) -> List[SessionEssence]:
        """All individual summary essences."""
        return list(self._summaries)

    def maybe_summarize(self, cycle: int,
                        chat_history: List[Dict]) -> Optional[SessionEssence]:
        """Check if a summary is due and generate one if so.

        Args:
            cycle: Current pipeline cycle number.
            chat_history: Full chat history list.

        Returns:
            SessionEssence if a summary was generated, else None.
        """
        if cycle - self._last_summary_cycle < self.summary_interval:
            return None

        # Only summarize if we have enough history
        history_since_last = chat_history[self._last_summary_cycle:]
        if len(history_since_last) < 4:
            return None

        essence = self._generate_summary(chat_history)
        if essence is not None:
            self._summaries.append(essence)
            self._running_essence = self._running_essence.merge(essence)
            self._last_summary_cycle = cycle
            logger.info(
                f"ContextSummarizer: essence generated at cycle {cycle} — "
                f"{len(essence.key_decisions)} decisions, "
                f"{len(essence.user_preferences)} preferences"
            )

        return essence

    def _generate_summary(self, chat_history: List[Dict]) -> Optional[SessionEssence]:
        """Call ollama_chat to generate a structured summary."""
        # Format the recent history for the prompt
        window = chat_history[-(self.max_history_before_summary):]

        # Format as readable conversation
        lines = []
        for msg in window:
            role = msg.get('role', 'unknown').upper()
            content = msg.get('content', '')
            # Truncate very long messages for the summarizer prompt
            if len(content) > 500:
                content = content[:500] + '... [truncated]'
            lines.append(f"[{role}] {content}")

        history_text = '\n'.join(lines)

        messages = [
            {"role": "system", "content": SUMMARIZER_PROMPT.format(history=history_text)},
        ]

        try:
            reply = self._ollama_chat(messages)
            return self._parse_essence(reply)
        except Exception as e:
            logger.warning(f"ContextSummarizer: LLM call failed: {e}")
            return None

    @staticmethod
    def _parse_essence(raw_json: str) -> Optional[SessionEssence]:
        """Parse the LLM response into a SessionEssence."""
        # Try to extract JSON from the response
        text = raw_json.strip()

        # Find JSON block between triple backticks if present
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0].strip()
        elif '```' in text:
            text = text.split('```')[1].split('```')[0].strip()

        # Try direct parse
        try:
            data = json.loads(text)
            return SessionEssence.from_dict(data)
        except json.JSONDecodeError:
            pass

        # Fallback: try to find a JSON object in the text
        try:
            start = text.index('{')
            end = text.rindex('}') + 1
            data = json.loads(text[start:end])
            return SessionEssence.from_dict(data)
        except (ValueError, json.JSONDecodeError):
            logger.warning(f"ContextSummarizer: failed to parse essence from: {text[:200]}...")
            return None

    def get_context_block(self) -> Dict:
        """Get the running essence as a context block for system prompts.

        Returns a dict that can be injected into the system prompt.
        """
        return {
            "session_essence": self._running_essence.to_dict(),
            "summary_count": len(self._summaries),
        }
