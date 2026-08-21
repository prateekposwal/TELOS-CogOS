"""
TELOS real-world action channels.

Deliberately small: the audited ActionExecutor is the ONLY real-tool channel.
Every command is allowlist-checked, firewall-audited, operator-permitted, and
trace-logged; a block is a first-class record (see executor.py for the full
pattern statement).
"""

from telos.core.actions.executor import (
    ACTION_ALLOWLIST, AllowlistEntry, ToolPermission, ActionExecution,
    ActionExecutor, ToolRejected,
)

__all__ = [
    "ACTION_ALLOWLIST", "AllowlistEntry", "ToolPermission", "ActionExecution",
    "ActionExecutor", "ToolRejected",
]
