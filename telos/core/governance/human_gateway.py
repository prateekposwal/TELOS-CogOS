"""
HumanGateway — Human-in-the-Loop for the Governance layer.

When the Council blocks an action or DI drops below threshold, the
Pipeline pauses and asks a human for review. The human can approve,
deny, or modify the intent before execution continues.

Usage:
    gateway = HumanGateway(mode="stdin")
    verdict = gateway.review(intent, council_signals, di)
    if verdict.approved:
        # proceed with execution
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable

logger = logging.getLogger('telos_human_gateway')


@dataclass
class HumanVerdict:
    approved: bool
    override_reason: str = ""
    modified_intent: Optional[Dict] = None
    reviewer: str = "human"
    timestamp: float = 0.0


class HumanGateway:
    """Pauses execution for human review when triggered.

    Modes:
      - stdin:   prompt on terminal (default)
      - webhook: POST to a URL with the review request
      - auto:    always approve (for testing/headless)
    """

    def __init__(self, mode: str = "auto",
                 webhook_url: Optional[str] = None,
                 auto_approve_threshold: float = 0.3,
                 sandbox: Any = None):
        self._mode = mode
        self._webhook_url = webhook_url
        self._auto_approve_threshold = auto_approve_threshold
        self._callbacks: List[Callable] = []
        self._reviews: List[Dict] = []
        # The governed egress channel for the webhook mode. When not injected it
        # is built lazily from the operator-configured webhook URL (the ONE
        # declared endpoint), so the request still passes host/port/route/bounds
        # gates instead of opening a raw http.client connection.
        self._sandbox = sandbox

    def _egress(self):
        """The NetworkSandbox owning this gateway's declared webhook endpoint.

        Returns:
            A NetworkSandbox whose only egress rule is the operator-configured
            webhook URL (exact host/port/route prefix, POST). An injected
            sandbox always wins so an operator can widen the allowlist.
        """
        if self._sandbox is not None:
            return self._sandbox
        from telos.core.actions.sandbox import EgressRule, NetworkSandbox
        import urllib.parse
        parsed = urllib.parse.urlparse(self._webhook_url or "")
        scheme = (parsed.scheme or "https").lower()
        host = parsed.hostname or ""
        port = parsed.port or (443 if scheme == "https" else 80)
        route = parsed.path or "/"
        self._sandbox = NetworkSandbox(rules=[
            EgressRule(host=host, ports=(port,), routes=(route,),
                       methods=("POST",)),
        ])
        return self._sandbox

    def on_review(self, callback: Callable) -> None:
        """Register callback fired on each review."""
        self._callbacks.append(callback)

    def should_review(self, council_validated: bool,
                      decision_integrity: float) -> bool:
        """Determine if human review is needed.
            Args:
                council_validated: the council_validated argument for this call.
                decision_integrity: the decision_integrity argument for this call.
        """
        if self._mode == "auto":
            return False
        if not council_validated:
            return True
        if decision_integrity < self._auto_approve_threshold:
            return True
        return False

    def review(self, intent: Any,
               council_signals: List[Dict[str, Any]],
               decision_integrity: float,
               mission_drift: float = 0.0,
               blocking_validator: Optional[str] = None,
               context: Optional[Dict] = None) -> HumanVerdict:
        """Pause and ask human to review the pending action.
            Args:
                intent: the intent being evaluated
                council_signals: the council_signals argument for this call.
                decision_integrity: the decision_integrity argument for this call.
                mission_drift: the mission_drift argument for this call.
                blocking_validator: the blocking_validator argument for this call.
                context: the context argument for this call.
        """
        review_data = {
            "timestamp": time.time(),
            "intent": str(intent),
            "council_signals": council_signals,
            "decision_integrity": round(decision_integrity, 3),
            "mission_drift": round(mission_drift, 3),
            "blocking_validator": blocking_validator,
            "context": context or {},
        }

        verdict = self._get_verdict(review_data)
        verdict.timestamp = time.time()
        self._reviews.append({
            **review_data,
            "verdict": verdict.approved,
            "reason": verdict.override_reason,
        })

        for cb in self._callbacks:
            try:
                cb(verdict, review_data)
            except Exception:
                logger.exception("HumanGateway callback failed")

        return verdict

    def _get_verdict(self, data: Dict) -> HumanVerdict:
        if self._mode == "stdin":
            return self._stdin_review(data)
        elif self._mode == "webhook" and self._webhook_url:
            return self._webhook_review(data)
        else:
            return HumanVerdict(approved=True,
                                override_reason="auto_approve",
                                reviewer="auto")

    def _stdin_review(self, data: Dict) -> HumanVerdict:
        print("\n" + "=" * 50)
        print("🤖 TELOS requires HUMAN REVIEW")
        print("=" * 50)
        print(f"Intent:        {data['intent']}")
        print(f"DI:            {data['decision_integrity']}")
        print(f"MD:            {data['mission_drift']}")
        print(f"Blocked by:    {data['blocking_validator'] or 'none'}")
        print(f"Council:       {len(data['council_signals'])} signals")
        for sig in data['council_signals']:
            status = "✅" if sig.get("passed") else "❌"
            print(f"  {status} {sig.get('validator')}: {sig.get('reason', '')}")
        print("-" * 50)
        while True:
            choice = input("Approve? (y/n/modify) [y]: ").strip().lower()
            if choice in ("", "y", "yes"):
                return HumanVerdict(approved=True,
                                    override_reason="human_approved",
                                    reviewer="human")
            elif choice in ("n", "no"):
                return HumanVerdict(approved=False,
                                    override_reason="human_denied",
                                    reviewer="human")
            elif choice == "modify":
                mod = input("Modification instructions: ").strip()
                return HumanVerdict(
                    approved=True,
                    override_reason=f"human_modified: {mod}",
                    modified_intent={"note": mod},
                    reviewer="human",
                )

    def _webhook_review(self, data: Dict) -> HumanVerdict:
        import json as _json
        try:
            result = self._egress().request(
                "POST", self._webhook_url, body=_json.dumps(data),
                headers={"Content-Type": "application/json"})
            if not result.allowed:
                raise RuntimeError(result.blocked_reason or "egress blocked")
            payload = _json.loads(result.body)
            approved = payload.get("approved", True)
            return HumanVerdict(
                approved=approved,
                override_reason=payload.get("reason", "webhook_decision"),
                reviewer="webhook",
            )
        except Exception as e:
            logger.warning(f"Webhook review failed ({e}), auto-approving")
            return HumanVerdict(approved=True,
                                override_reason=f"webhook_fallback: {e}",
                                reviewer="auto")

    @property
    def stats(self) -> Dict:
        total = len(self._reviews)
        approved = sum(1 for r in self._reviews if r["verdict"])
        return {
            "total_reviews": total,
            "approved": approved,
            "denied": total - approved,
            "mode": self._mode,
        }
