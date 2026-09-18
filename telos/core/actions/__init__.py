"""
TELOS real-world action channels.

Deliberately small: the audited ActionExecutor is the ONLY real-tool channel.
Every command is allowlist-checked, firewall-audited, operator-permitted, and
trace-logged; a block is a first-class record (see executor.py for the full
pattern statement).

The executable tool set is declared EXACTLY ONCE in ``registry.py`` (the
canonical ToolRegistry); the executor's ACTION_ALLOWLIST is a projection of it.
"""

from telos.core.actions.registry import (
    ToolSpec, AllowlistEntry, ToolRegistry, DEFAULT_REGISTRY,
)
from telos.core.actions.executor import (
    ACTION_ALLOWLIST, ToolPermission, ActionExecution,
    ActionExecutor, ToolRejected,
)

__all__ = [
    "ACTION_ALLOWLIST", "AllowlistEntry", "ToolSpec", "ToolRegistry",
    "DEFAULT_REGISTRY",
    "ToolPermission", "ActionExecution",
    "ActionExecutor", "ToolRejected",
]
