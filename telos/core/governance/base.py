"""
Governance — Cognitive Confidentiality Layer for TELOS

This module defines the core types used across the Governance subsystem.
Governance is NOT security (RBAC/ABAC). It is Epistemic Governance:
governing when, why, and to whom truth is revealed based on mission
context, timing, and recipient capacity to act constructively.

Principle of Cognitive Confidentiality:
    "Intelligence includes knowing not only what is true, but also when,
    why, and to whom that truth should be revealed."
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class AccessLevel(Enum):
    """What a stream/actor is authorized to access."""
    OBSERVE = "observe"       # Can read public facts
    ANALYZE = "analyze"       # Can access historical context
    ACTUATE = "actuate"       # Can trigger state changes
    CLASSIFIED = "classified" # Requires specific mission clearance


class ReadinessState(Enum):
    """Lifecycle state of a fact in the knowledge base."""
    LOCKED = "locked"         # Exists but not yet releasable
    PENDING = "pending"       # Conditions partially met
    READY = "ready"           # Fully releasable
    EXPIRED = "expired"       # No longer relevant


@dataclass
class ReadinessCondition:
    """A condition that must be met before a fact becomes ready."""
    condition_type: str  # "cycle_count", "signal_detected", "mission_match"
    threshold: float
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FirewallVerdict:
    """The output of the Decision Firewall — final pre-execution check."""
    passed: bool
    reason: str
    blocked_by: Optional[str] = None
    governance_signals: List[Dict] = field(default_factory=list)


@dataclass
class GovernanceReport:
    """Summary of governance actions in a single decision cycle."""
    stream_access_grants: int = 0
    stream_access_denials: int = 0
    locked_facts: int = 0
    ready_facts: int = 0
    firewall_blocked: bool = False
    firewall_reason: str = ""
