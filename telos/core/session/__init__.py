"""
TELOS Session Package — Continuity, Handoff, Context Management, and Checkpoint CLI.

Provides:
    - AgentsWriter: Auto-generates structured session summaries for AGENTS.md
    - SessionSummary: Dataclass for structured session handoff data
    - SessionCheckpoint: Dataclass for lossless save/restore of full session state
    - CheckpointCLI: Save/load/list/restore session checkpoints
    - CLI entry points for `telos session` subcommands

Axioms: 4.7 (System Memory), 5.1 (Self-Preservation), 2.4 (Path Dependency)
"""

from telos.core.session.agents_writer import AgentsWriter, SessionSummary
from telos.core.session.checkpoint_cli import (
    SessionCheckpoint,
    CheckpointCLI,
    cmd_save,
    cmd_list,
    cmd_load,
    cmd_restore,
    main as checkpoint_cli_main,
)

__all__ = [
    "AgentsWriter",
    "SessionSummary",
    "SessionCheckpoint",
    "CheckpointCLI",
    "cmd_save",
    "cmd_list",
    "cmd_load",
    "cmd_restore",
    "checkpoint_cli_main",
]
