"""Checkpoint CLI commands."""
import os
import sys
import json
import logging
from datetime import datetime
from typing import Dict, Optional, List
from telos.core.session.checkpoint import SessionCheckpoint, CheckpointCLI, DEFAULT_SESSION_ROOT


logger = logging.getLogger('telos_checkpoint_cli')
def _auto_session_name() -> str:
    """Generate an auto-session name from the current timestamp."""
    return datetime.now().strftime("session_%Y%m%d_%H%M%S_%f")


def cmd_save(args: Optional[List[str]] = None) -> None:
    """CLI handler for `telos session save [--name NAME]`."""
    import argparse
    parser = argparse.ArgumentParser(description="Save session checkpoint")
    parser.add_argument("--name", "-n", default=None, help="Session name")
    parsed, _ = parser.parse_known_args(args)

    name = parsed.name or _auto_session_name()
    cli = CheckpointCLI()
    path = cli.save(
        session_name=name,
        cycle_count=0,
        chat_history=[],
        summary="Manual save via CLI",
    )
    print(f"✅ Session saved: {path}")


def cmd_list(args: Optional[List[str]] = None) -> None:
    """CLI handler for `telos session list`."""
    cli = CheckpointCLI()
    sessions = cli.list_sessions()
    if not sessions:
        print("📭 No saved sessions found.")
        return

    print(f"📁 Saved Sessions ({len(sessions)}):")
    print(f"{'Name':<30} {'Time':<22} {'Cycles':<8} {'Summary'}")
    print("-" * 80)
    for s in sessions:
        print(
            f"{s['name']:<30} {s['formatted_time']:<22} "
            f"{s['cycle_count']:<8} {s['summary']}"
        )


def cmd_load(args: Optional[List[str]] = None) -> None:
    """CLI handler for `telos session load --name NAME`.

    Prints restore instructions + outputs AGENTS.md block.
    """
    import argparse
    parser = argparse.ArgumentParser(description="Load session checkpoint")
    parser.add_argument("--name", "-n", required=True, help="Session name")
    parsed, _ = parser.parse_known_args(args)

    cli = CheckpointCLI()
    prompt = cli.generate_continuation_prompt(parsed.name)
    if prompt is None:
        print(f"❌ Session '{parsed.name}' not found.")
        return

    print(prompt)


def cmd_restore(args: Optional[List[str]] = None) -> None:
    """CLI handler for `telos session restore --name NAME`.

    Restores checkpoint + writes a continuation prompt to stdout.
    """
    cmd_load(args)


def main() -> None:
    """Main entry point: `telos session <command> [args]`.

    Commands:
        save    — Save current session state
        list    — List all saved sessions
        load    — Load and print restore instructions
        restore — Alias for load
    """
    import sys

    if len(sys.argv) < 3 or sys.argv[1] != "session":
        print("Usage: telos session <command> [args]")
        print("Commands: save, list, load, restore")
        sys.exit(1)

    command = sys.argv[2]
    args = sys.argv[3:] if len(sys.argv) > 3 else []

    commands = {
        "save": cmd_save,
        "list": cmd_list,
        "load": cmd_load,
        "restore": cmd_restore,
    }

    if command in commands:
        commands[command](args)
    else:
        print(f"Unknown command: {command}")
        print("Available: save, list, load, restore")
        sys.exit(1)


if __name__ == "__main__":
    main()
