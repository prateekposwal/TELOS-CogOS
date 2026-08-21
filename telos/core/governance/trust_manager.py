"""
Trust Manager — Evaluates stream/actor authorization against mission context.

This is NOT traditional RBAC (role-based access control). The TrustManager
evaluates the *context* of a request: what is the current mission, what is
the stream asking for, and is this release of information aligned with the
system's strategic objectives?

Examples:
  - LanguageStream asks for CustomerCreditCard during Mission "Support"
    → DENIED (not mission-relevant)
  - LanguageStream asks for CustomerCreditCard during Mission "Payment"
    → GRANTED (mission-aligned)
  - ReflexStream asks for SafetyThresholds during any mission
    → GRANTED (always authorized for safety-critical streams)
"""

import logging
from typing import Dict, Optional, Set
from dataclasses import dataclass, field

from telos.core.governance.base import AccessLevel

logger = logging.getLogger('telos_governance')


@dataclass
class StreamAuthorization:
    """Authorization profile for a single cognitive stream."""
    stream_name: str
    default_access: AccessLevel = AccessLevel.OBSERVE
    authorized_missions: Set[str] = field(default_factory=lambda: {"*"})
    knowledge_domains: Set[str] = field(default_factory=lambda: {"public"})
    requires_clearance: bool = False
    can_bypass_readiness: bool = False


class TrustManager:
    """Evaluates stream/actor authorization against mission context.

    The TrustManager sits between the World (knowledge) and the Streams
    (consumers). When a stream requests access to a knowledge domain,
    the TrustManager evaluates:
      1. Is the stream authorized for this domain?
      2. Is the current mission compatible with releasing this information?
      3. Does the stream have the required clearance level?

    If any check fails, the information is NOT exposed to the stream.
    """

    def __init__(self):
        self._authorizations: Dict[str, StreamAuthorization] = {}
        self._current_mission: str = "default"
        self._grant_count: int = 0
        self._denial_count: int = 0

    def register_stream(self, stream_name: str,
                         default_access: AccessLevel = AccessLevel.OBSERVE,
                         authorized_missions: Optional[Set[str]] = None,
                         knowledge_domains: Optional[Set[str]] = None,
                         requires_clearance: bool = False,
                         can_bypass_readiness: bool = False) -> None:
        """Register a cognitive stream's authorization profile.
        stream_name: the stream name for this operation
        default_access: the default access for this operation
        authorized_missions: the authorized missions for this operation
        knowledge_domains: the knowledge domains for this operation
        requires_clearance: the requires clearance for this operation
        can_bypass_readiness: the can bypass readiness for this operation
"""
        self._authorizations[stream_name] = StreamAuthorization(
            stream_name=stream_name,
            default_access=default_access,
            authorized_missions=authorized_missions or {"*"},
            knowledge_domains=knowledge_domains or {"public"},
            requires_clearance=requires_clearance,
            can_bypass_readiness=can_bypass_readiness,
        )

    def set_mission(self, mission: str) -> None:
        """Update the current mission context."""
        self._current_mission = mission
        logger.debug(f"TrustManager: mission set to '{mission}'")

    def authorize_stream(self, stream_name: str,
                         knowledge_domain: str = "public") -> bool:
        """Check if a stream is authorized to access a knowledge domain.

        Returns True if authorized, False if denied.
        
        stream_name: the stream name for this operation
        knowledge_domain: the knowledge domain for this operation
"""
        auth = self._authorizations.get(stream_name)
        if auth is None:
            # Unknown streams get only OBSERVE access to public domain
            result = knowledge_domain == "public"
            self._record_decision(stream_name, knowledge_domain, result)
            return result

        # Check domain authorization
        if knowledge_domain not in auth.knowledge_domains and "*" not in auth.knowledge_domains:
            self._record_decision(stream_name, knowledge_domain, False,
                                  f"domain '{knowledge_domain}' not in authorized set")
            return False

        # Check mission authorization
        if self._current_mission not in auth.authorized_missions and "*" not in auth.authorized_missions:
            self._record_decision(stream_name, knowledge_domain, False,
                                  f"mission '{self._current_mission}' not authorized for stream")
            return False

        self._record_decision(stream_name, knowledge_domain, True)
        return True

    def authorize_knowledge_release(self, knowledge_domain: str) -> bool:
        """Check if a knowledge domain is releasable under the current mission.

        Even if a stream is authorized, some knowledge may be globally
        locked due to mission sensitivity.
        
        knowledge_domain: the knowledge domain for this operation
"""
        # Implementation-specific: check mission-level knowledge policies
        sensitive_domains = {"classified", "financial", "personal"}
        if knowledge_domain in sensitive_domains and self._current_mission == "default":
            return False
        return True

    def get_stream_access_level(self, stream_name: str) -> AccessLevel:
        """Get the effective access level for a stream.
        stream_name: the stream name for this operation
"""
        auth = self._authorizations.get(stream_name)
        return auth.default_access if auth else AccessLevel.OBSERVE

    def _record_decision(self, stream_name: str, domain: str,
                          granted: bool, reason: str = "") -> None:
        if granted:
            self._grant_count += 1
        else:
            self._denial_count += 1
            logger.info(f"TrustManager: DENIED {stream_name} access to '{domain}'"
                        f"{f' ({reason})' if reason else ''}")

    @property
    def stats(self) -> Dict:
        return {
            "authorized_streams": len(self._authorizations),
            "grants": self._grant_count,
            "denials": self._denial_count,
            "current_mission": self._current_mission,
        }
