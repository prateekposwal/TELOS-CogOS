"""
Conversation Knowledge Ingestion — Remembering User Preferences Across Sessions.

After each pipeline cycle, this module extracts structured facts from the
conversation (user intent, DI, MD, blockers, preferences) and records them
in the KnowledgeGraph. At the start of each pipeline cycle, it queries the
KG for relevant past context about the user, making TELOS remember who the
user is and what they prefer across sessions.

No new storage — piggybacks on the existing persistent KnowledgeGraph via
KnowledgeManager's search_knowledge / consult_knowledge APIs.

Records as KG nodes tagged with:
  - domain: "conversation" or "user_preference"
  - tags: ["conversation", "user_feedback", "cycle_<N>", user_name]

Axioms: 2.3 (Kintsugi), 2.4 (Path Dependency), 4.1 (Identity Shapes Decisions), 4.7 (System Memory)
"""

from __future__ import annotations

import json
import time
import logging
from typing import List, Dict, Optional, Any, Callable

logger = logging.getLogger('telos_knowledge_ingestion')

# Domain constants for the KnowledgeGraph
DOMAIN_CONVERSATION = "conversation"
DOMAIN_USER_PREFERENCE = "user_preference"
DOMAIN_BLOCKER = "blocker"
DOMAIN_INTENT = "intent_pattern"


class ConversationKnowledgeIngestion:
    """Extracts structured conversation facts and records them in the KG.

    Two-phase operation:
      1. pre_cycle():   Query KG for relevant past context about the user.
      2. post_cycle():   Extract facts from current cycle and record in KG.

    Usage in telos_task.py:
        kg_ingestion = ConversationKnowledgeIngestion(
            search_fn=pipeline.infra_manager.knowledge_manager.search_knowledge,
            consult_fn=pipeline.infra_manager.knowledge_manager.consult_knowledge,
            record_fn=pipeline.infra_manager.knowledge.record,
        )
        # Before cycle:
        context = kg_ingestion.pre_cycle(user_name, cycle)
        # After cycle:
        kg_ingestion.post_cycle(user_name, cycle, result, chat_history)
    """

    def __init__(self,
                 search_fn: Callable,
                 consult_fn: Callable,
                 record_fn: Callable):
        """
        Args:
            search_fn:  Function(domain, top_k) → List[ProjectNode]
                        (from KnowledgeManager.search_knowledge)
            consult_fn: Function(domain, cycle) → Dict
                        (from KnowledgeManager.consult_knowledge)
            record_fn:  Function(domain, approach, outcome, ...) → str
                        (from KnowledgeGraph.record)
        """
        self._search = search_fn
        self._consult = consult_fn
        self._record = record_fn
        self._known_preferences: Dict[str, List[str]] = {}
        self._last_extraction: int = 0

    def pre_cycle(self, user_name: str, cycle: int) -> Dict:
        """Query KG for past context about this user before the cycle runs.

        Returns a context dict with:
          - known_user: bool
          - known_preferences: list of known preference strings
          - past_approaches: list of past intent approaches used
          - past_failures: list of past blockers/failures
          - consultation: knowledge consultation report
        """
        context: Dict[str, Any] = {
            "known_user": False,
            "known_preferences": [],
            "past_approaches": [],
            "past_failures": [],
            "consultation": {},
        }

        # 1. Query for user preferences
        user_domain = f"{DOMAIN_USER_PREFERENCE}/{user_name}"
        prefs = self._search(domain=user_domain, top_k=5)
        if prefs:
            context["known_user"] = True
            context["known_preferences"] = [
                p.approach for p in prefs if hasattr(p, 'approach')
            ]
            logger.debug(f"KG Ingestion: found {len(prefs)} preferences for {user_name}")

        # 2. Query for past conversation patterns
        conv_domain = f"{DOMAIN_CONVERSATION}/{user_name}"
        conv_results = self._search(domain=conv_domain, top_k=5)
        if conv_results:
            context["past_approaches"] = [
                p.approach for p in conv_results if hasattr(p, 'approach')
            ]

        # 3. Query for past blockers
        blocker_domain = f"{DOMAIN_BLOCKER}/{user_name}"
        blockers = self._search(domain=blocker_domain, top_k=3)
        if blockers:
            context["past_failures"] = [
                {"approach": p.approach, "reason": getattr(p, 'failure_reason', None)}
                for p in blockers
                if hasattr(p, 'approach')
            ]

        # 4. Do a full knowledge consultation
        try:
            consultation = self._consult(domain=user_domain, cycle=cycle)
            context["consultation"] = consultation
        except Exception as e:
            logger.debug(f"KG Ingestion: consultation skipped: {e}")

        return context

    def post_cycle(self, user_name: str, cycle: int,
                   result: Any, chat_history: List[Dict]) -> None:
        """Extract facts from the current cycle and record in KG.

        Records:
          - User's expressed intent as a conversation node
          - Blocking events as blocker nodes
          - High-mission-drift events as failure nodes
          - Decision integrity scores as quality nodes

        Args:
            user_name: The user's name.
            cycle: Current pipeline cycle number.
            result: PipelineResult from pipeline.execute()
            chat_history: The full chat history list.
        """
        trace = getattr(result, 'decision_trace', None)
        if trace is None:
            return

        di = getattr(trace, 'decision_integrity', 1.0)
        md = getattr(trace, 'mission_drift', 0.0)
        council_blocked = getattr(result, 'council_blocked', False)
        firewall_blocked = getattr(result, 'firewall_blocked', False)
        selected_intent = getattr(trace, 'selected_intent', None)
        intent_type = getattr(selected_intent, 'intent_type', 'unknown') if selected_intent else 'unknown'

        # --- Record user intent as conversation node ---
        conv_domain = f"{DOMAIN_CONVERSATION}/{user_name}"
        outcome = max(0.0, min(1.0, di))
        self._record(
            domain=conv_domain,
            approach=intent_type,
            outcome=outcome,
            tags=["conversation", f"cycle_{cycle}", user_name, "pipeline"],
            params={
                "cycle": cycle,
                "di": round(di, 3),
                "md": round(md, 3),
                "council_blocked": council_blocked,
            },
        )

        # --- Record blocker if council or firewall blocked ---
        if council_blocked or firewall_blocked:
            blocker_reason = (
                getattr(trace, 'blocking_validator', None)
                or getattr(trace, 'firewall_blocked_by', None)
                or "unknown_blocker"
            )
            blocker_domain = f"{DOMAIN_BLOCKER}/{user_name}"
            self._record(
                domain=blocker_domain,
                approach=f"blocked_{intent_type}",
                outcome=0.1,
                tags=["blocker", f"cycle_{cycle}", user_name, "failure"],
                params={
                    "cycle": cycle,
                    "reason": blocker_reason,
                    "di": round(di, 3),
                    "md": round(md, 3),
                },
            )

        # --- Record high mission drift as a warning signal ---
        if md > 0.5:
            drift_domain = f"{DOMAIN_CONVERSATION}/{user_name}"
            self._record(
                domain=drift_domain,
                approach=f"high_drift_{intent_type}",
                outcome=max(0.0, 1.0 - md),
                tags=["drift", f"cycle_{cycle}", user_name, "warning"],
                params={
                    "cycle": cycle,
                    "md": round(md, 3),
                    "di": round(di, 3),
                },
            )

        # --- Extract user preferences from chat history ---
        # Look at the most recent user message for preference signals
        if chat_history:
            last_user_msg = None
            for msg in reversed(chat_history):
                if msg.get('role') == 'user':
                    last_user_msg = msg.get('content', '')
                    break

            if last_user_msg:
                content_lower = last_user_msg.lower()
                extracted_prefs = []

                # Detect preference signals
                if any(w in content_lower for w in ['prefer', 'rather', 'better if',
                                                      'i like', 'i want', 'please']):
                    # Use a hash of the user message as a unique key to avoid duplicates
                    pref_key = f"user_said_{hash(last_user_msg) % 1000000}"
                    extracted_prefs.append((pref_key, last_user_msg[:200]))

                # Detect name/introduction signals
                if any(w in content_lower for w in ['call me', 'my name is',
                                                      "i'm ", 'i am ']):
                    pref_key = f"intro_{hash(last_user_msg) % 1000000}"
                    extracted_prefs.append((pref_key, last_user_msg[:200]))

                # Record extracted preferences
                for pref_key, pref_content in extracted_prefs:
                    pref_domain = f"{DOMAIN_USER_PREFERENCE}/{user_name}"
                    self._record(
                        domain=pref_domain,
                        approach=pref_key,
                        outcome=0.9,  # high confidence for explicit preferences
                        tags=["preference", user_name, "conversation"],
                        params={
                            "content": pref_content,
                            "cycle": cycle,
                        },
                    )

        self._last_extraction = cycle
        logger.debug(
            f"KG Ingestion: recorded cycle {cycle} for {user_name} "
            f"(intent={intent_type}, DI={di:.2f}, MD={md:.2f})"
        )

    def summarize_user_knowledge(self, user_name: str) -> Dict:
        """Get a summary of what the KG knows about a user.

        Returns:
            Dict with preferences, past intents, blockers.
        """
        prefs = self._search(domain=f"{DOMAIN_USER_PREFERENCE}/{user_name}", top_k=10)
        convs = self._search(domain=f"{DOMAIN_CONVERSATION}/{user_name}", top_k=10)
        blockers = self._search(domain=f"{DOMAIN_BLOCKER}/{user_name}", top_k=5)

        return {
            "user_name": user_name,
            "known_preferences": [
                {"key": p.approach, "content": p.params.get('content', '')}
                for p in prefs
            ],
            "past_intents": [
                {"type": p.approach, "outcome": p.outcome}
                for p in convs
            ],
            "past_blockers": [
                {"type": p.approach, "reason": getattr(p, 'failure_reason', None)}
                for p in blockers
            ],
        }
