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
    "DEFAULT_CERTIFICATION_PATH",
    "WorldAdapter", "WorldObservation", "ValidationResult", "VerificationResult",
    "AdapterRefused", "FilesystemWriteAdapter",
    "ActionMode", "LiveApproval", "WorldActionProposal", "WorldActionResult",
    "WorldActionRunner",
]
