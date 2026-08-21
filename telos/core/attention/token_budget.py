"""
TokenBudgetManager — Intelligent Chat History Truncation by Signal Value.

Replaces the naive chat_history[-4:] approach with signal-weighted
token budgeting. Each message is scored by its decision-signal value:

    High signal = low DI, high mission drift, council blocks, escalations

The manager keeps the highest-signal messages plus the last 2 conversational
turns, all within a configurable token budget. Purely algorithmic — zero LLM calls.

Uses:
    - TokenBudgetManager.optimize(chat_history) → truncated list
    - TokenBudgetManager.score_message(msg) → float signal score

Axioms: 1.2 (Process over Outcomes), 2.4 (Path Dependency), 4.7 (System Memory)
"""

from __future__ import annotations

import re
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger('telos_token_budget')

DEFAULT_TOKEN_BUDGET = 2048
DEFAULT_KEEP_LAST_N = 2
AVG_CHARS_PER_TOKEN = 4.0  # rough heuristic for fast estimation


def estimate_tokens(text: str) -> int:
    """Fast token-count estimate without calling a tokenizer.
        Args:
            text: the text argument for this call.
    """
    return int(len(text) / AVG_CHARS_PER_TOKEN + 0.5)


def estimate_message_tokens(msg: Dict) -> int:
    """Estimate tokens for a chat message dict (role + content).
        Args:
            msg: the msg argument for this call.
    """
    # role adds ~4 tokens, content + overhead per message ~8 tokens
    overhead = 12
    content = msg.get('content', '') or ''
    return estimate_tokens(content) + overhead


class TokenBudgetManager:
    """Intelligent chat-history truncation using signal-weighted selection.

    Scoring signals (higher = more important to keep):
      - DI < 0.5: low decision integrity → high signal
      - mission_drift > 0.3: divergence from mission → high signal
      - council_blocked: a block event is always high-signal
      - escalation: escalations are always high-signal
      - user is always high-signal (the human's input matters)
      - assistant explanations get a small recency bonus

    Strategy:
      1. Always keep the last N conversational turns (default 2).
      2. Score all remaining messages by signal value.
      3. Fill the remaining token budget with highest-signal messages.
      4. If budget is exceeded, drop lowest-signal messages first.
    """

    def __init__(self,
                 token_budget: int = DEFAULT_TOKEN_BUDGET,
                 keep_last_n: int = DEFAULT_KEEP_LAST_N):
        self.token_budget = token_budget
        self.keep_last_n = keep_last_n

    @staticmethod
    def score_message(msg: Dict,
                      trace: Optional[Dict] = None) -> float:
        """Score a single message by its signal value.

        Args:
            msg: A chat message dict {'role': ..., 'content': ..., ...}
            trace: Optional decision trace dict with DI, MD, block info.

        Returns:
            Float score in [0.0, 2.0] where higher = more valuable to keep.
        """
        role = msg.get('role', '')
        content = msg.get('content', '') or ''
        score = 0.0

        # --- Role-based base scores ---
        if role == 'user':
            score += 0.8  # user input is always valuable
        elif role == 'system':
            score += 0.5  # system prompts provide context
        elif role == 'assistant':
            score += 0.3  # assistant replies carry explanations

        # --- Content-based signals ---
        content_lower = content.lower()

        # Escalation keywords
        if any(w in content_lower for w in ['escalat', 'override', 'human in the loop',
                                              'escalation requested', 'emergency']):
            score += 0.6

        # Block / council keywords
        if any(w in content_lower for w in ['blocked', 'rejected', 'vetoed', 'dissent',
                                              'council block', 'firewall']):
            score += 0.5

        # Decision / strategy keywords
        if any(w in content_lower for w in ['decision', 'selected', 'intent',
                                              'strategy', 'navigate', 'approach']):
            score += 0.3

        # Error / failure keywords
        if any(w in content_lower for w in ['error', 'fail', 'crash', 'stuck',
                                              'obstacle', 'cannot']):
            score += 0.4

        # User preference / identity keywords
        if any(w in content_lower for w in ['prefer', 'like', 'want', 'dont', "don't",
                                              'remember', 'call me', 'my name']):
            score += 0.4

        # --- Trace-based signals (if provided) ---
        if trace:
            di = trace.get('di', 1.0)
            md = trace.get('md', 0.0)
            blocked = trace.get('blocked', False)
            escalated = trace.get('escalated', False)

            if di < 0.5:
                score += 0.6  # low DI = important to understand why
            if md > 0.3:
                score += 0.5  # high drift = mission divergence
            if blocked:
                score += 0.7  # blocks are crucial signals
            if escalated:
                score += 0.8  # escalations are critical

        # Length penalty: very long messages consume disproportionate budget
        tokens = estimate_tokens(content)
        if tokens > 200:
            score -= 0.1
        if tokens > 500:
            score -= 0.2

        return max(0.0, min(2.0, score))

    def optimize(self,
                 chat_history: List[Dict],
                 traces: Optional[Dict[int, Dict]] = None) -> List[Dict]:
        """Truncate chat_history to stay within token budget while
        preserving maximum signal.

        Args:
            chat_history: List of message dicts with 'role', 'content'.
            traces: Optional dict mapping message index → trace dict
                    with 'di', 'md', 'blocked', 'escalated'.

        Returns:
            Truncated list of messages fitting within token_budget.
        """
        if not chat_history:
            return []

        traces = traces or {}
        n = len(chat_history)

        # 1. Always keep the last N turns (each turn = user + assistant = 2 msgs)
        keep_count = min(self.keep_last_n * 2, n)
        protected = chat_history[-keep_count:]
        protected_tokens = sum(estimate_message_tokens(m) for m in protected)

        # 2. Score the unprotected messages
        unprotected = list(enumerate(chat_history[:-keep_count])) if n > keep_count else []

        scored: List[Tuple[float, int, Dict]] = []
        for idx, msg in unprotected:
            trace = traces.get(idx, {})
            score = self.score_message(msg, trace)
            scored.append((score, idx, msg))

        # 3. Sort by score descending
        scored.sort(key=lambda x: -x[0])

        # 4. Fill remaining budget with highest-signal messages
        budget_remaining = self.token_budget - protected_tokens
        selected: List[Tuple[int, Dict]] = []

        for score, idx, msg in scored:
            msg_tokens = estimate_message_tokens(msg)
            if msg_tokens <= budget_remaining:
                selected.append((idx, msg))
                budget_remaining -= msg_tokens
            elif budget_remaining > self.token_budget * 0.1:
                # If we have >10% budget left, try truncating the content
                # of this message instead of dropping it entirely
                content = msg.get('content', '') or ''
                role = msg.get('role', '')
                max_chars = int(budget_remaining * AVG_CHARS_PER_TOKEN)
                if max_chars > 50:  # only truncate if worthwhile
                    truncated = content[:max_chars] + '... [truncated]'
                    selected.append((idx, {'role': role, 'content': truncated}))
                    budget_remaining = 0

        # 5. Merge selected + protected, sort by original position
        selected.sort(key=lambda x: x[0])
        result = [msg for _, msg in selected] + protected

        kept_tokens = sum(estimate_message_tokens(m) for m in result)
        logger.debug(
            f"TokenBudget: {len(chat_history)}→{len(result)} msgs, "
            f"{kept_tokens}/{self.token_budget} tokens used"
        )
        return result

    @staticmethod
    def make_trace(di: float = 1.0, md: float = 0.0,
                   blocked: bool = False, escalated: bool = False) -> Dict:
        """Helper to build a trace dict from pipeline values.
            Args:
                md: the md argument for this call.
                blocked: the blocked argument for this call.
                escalated: the escalated argument for this call.
        """
        return {
            'di': di,
            'md': md,
            'blocked': blocked,
            'escalated': escalated,
        }
