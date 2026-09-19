"""
TELOS real-world action channels.

Deliberately small: the audited ActionExecutor is the ONLY real-tool channel.
Every command is allowlist-checked, firewall-audited, operator-permitted, and
trace-logged; a block is a first-class record (see executor.py for the full
pattern statement).

The executable tool set is declared EXACTLY ONCE in ``registry.py`` (the
canonical ToolRegistry); the executor's ACTION_ALLOWLIST is a projection of it.

The real-world action path adds two typed layers above the executor:
``world_adapter.py`` (the WorldAdapter capability contract) and
``world_action.py`` (the dry-run / controlled-LIVE runner). Certification is
per-capability (``certification.py``).
"""

from telos.core.actions.registry import (
    ToolSpec, AllowlistEntry, ToolRegistry, DEFAULT_REGISTRY,
)
from telos.core.actions.executor import (
    ACTION_ALLOWLIST, ToolPermission, ActionExecution,
    ActionExecutor, ToolRejected,
)
from telos.core.actions.certification import (
    CertificationRecord, CapabilityCertification, DEFAULT_CERTIFICATION_PATH,
    DEFAULT_SANDBOX_EVIDENCE_PATH, CertificationTier, load_sandbox_evidence,
    CertificationAction, VerifiedOutcome, CertificationDecision,
    CertificationWorkflow,
)
from telos.core.actions.durability import (
    SCHEMA_VERSION, KIND_AUTHORITY_EVIDENCE, StateOutcome, DurabilityMode,
    StateLoadResult, atomic_write_state, read_state,
)
from telos.core.actions.integrity import (
    IntegrityAnchor, IntegrityMode, LocalAnchor, HmacAnchor, WitnessAnchor,
    UnavailableAnchor, AnchorUnavailable, resolve_anchor, load_hmac_key,
)
from telos.core.actions.trust_anchor import (
    TrustVerdict, TrustVerification, WitnessScope, WitnessRecord,
    TrustAnchor, DisabledTrustAnchor, UnavailableTrustAnchor,
    ExternalHttpTrustAnchor, TrustAnchorUnavailable, TrustAnchorConflict,
    resolve_trust_anchor,
)
from telos.core.actions.reality_loop import (
    GAP_METRIC, text_reality_gap, observation_fingerprint,
    AuthorityState, CapabilityAuthority,
)
from telos.core.actions.world_adapter import (
    WorldAdapter, WorldObservation, ValidationResult, VerificationResult,
    AdapterRefused, FilesystemWriteAdapter,
)
from telos.core.actions.world_action import (
    ActionMode, LiveApproval, WorldActionProposal, WorldActionResult,
    WorldActionRunner,
)

__all__ = [
    "ACTION_ALLOWLIST", "AllowlistEntry", "ToolSpec", "ToolRegistry",
    "DEFAULT_REGISTRY",
    "ToolPermission", "ActionExecution",
    "ActionExecutor", "ToolRejected",
    "CertificationRecord", "CapabilityCertification",
    "DEFAULT_CERTIFICATION_PATH", "DEFAULT_SANDBOX_EVIDENCE_PATH",
    "CertificationTier", "load_sandbox_evidence",
    "CertificationAction", "VerifiedOutcome", "CertificationDecision",
    "CertificationWorkflow",
    "SCHEMA_VERSION", "KIND_AUTHORITY_EVIDENCE", "StateOutcome",
    "DurabilityMode", "StateLoadResult", "atomic_write_state", "read_state",
    "IntegrityAnchor", "IntegrityMode", "LocalAnchor", "HmacAnchor",
    "WitnessAnchor", "UnavailableAnchor", "AnchorUnavailable",
    "resolve_anchor", "load_hmac_key",
    "TrustVerdict", "TrustVerification", "WitnessScope", "WitnessRecord",
    "TrustAnchor", "DisabledTrustAnchor", "UnavailableTrustAnchor",
    "ExternalHttpTrustAnchor", "TrustAnchorUnavailable", "TrustAnchorConflict",
    "resolve_trust_anchor",
    "GAP_METRIC", "text_reality_gap", "observation_fingerprint",
    "AuthorityState", "CapabilityAuthority",
    "WorldAdapter", "WorldObservation", "ValidationResult", "VerificationResult",
    "AdapterRefused", "FilesystemWriteAdapter",
    "ActionMode", "LiveApproval", "WorldActionProposal", "WorldActionResult",
    "WorldActionRunner",
]
