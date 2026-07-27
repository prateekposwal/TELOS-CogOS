"""
Session Checkpoint CLI — Lossless Save & Restore of Full Session State.

Provides:
    - SessionCheckpoint: dataclass for serializable full session state
    - CheckpointCLI: save/load/list/restore operations
    - CLI entry points routed from telos/__init__.py

Save format (directory):
    /tmp/telos_sessions/<name>/
    ├── session.json              # SessionCheckpoint as JSON
    ├── chat_history.json         # Raw chat history
    ├── truncated_history.json    # TokenBudgetManager optimized history
    ├── essence.json              # ContextSummarizer session essence
    ├── agents.md                 # Snapshot of AGENTS.md at save time
    └── checkpoint_ref.txt        # Path to pipeline checkpoint file

Axioms: 4.7 (System Memory), 5.1 (Self-Preservation), 2.4 (Path Dependency)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger('telos_session_checkpoint')

DEFAULT_SESSION_ROOT = "/tmp/telos_sessions"
CONTINUATION_PROMPT_TEMPLATE = """# 🔄 Session Restored: {session_name}

Session saved at: {timestamp}
Session essence: {summary}

## Restore Instructions

1. Load pipeline checkpoint:
   ```bash
   python3 -c "from telos.core.infra_manager.checkpoint_manager import CheckpointManager; mgr = CheckpointManager('{checkpoint_dir}'); data = mgr.load(); print('Checkpoint loaded: cycle', data.cycle if data else 'N/A')"
   ```

2. The following AGENTS.md block was captured at save time — include it in your new session's context to restore awareness:

{agents_md_block}

3. Chat history ({chat_count} messages) and truncated history ({truncated_count} messages) are available in:
   - {chat_history_path}
   - {truncated_history_path}

4. Session essence (from ContextSummarizer):
   {essence_json}

## Quick Start
Continue working by loading the checkpoint and restoring chat context.
"""


@dataclass
class SessionCheckpoint:
    """Complete snapshot of a TELOS session for lossless save/restore.

    Fields:
        timestamp: Unix timestamp of save time
        cycle_count: Pipeline cycle count at save
        session_essence: Dict from ContextSummarizer (key_decisions, etc.)
        truncated_history: TokenBudgetManager-optimized message list
        chat_history: Last N turns of raw conversation
        pipeline_checkpoint_path: Path to the pipeline checkpoint file
        agents_md_content: Snapshot of AGENTS.md at save time
        summary: One-line human-readable summary of what was happening
    """
    timestamp: float
    cycle_count: int
    session_essence: Optional[Dict[str, Any]] = None
    truncated_history: Optional[List[Dict[str, Any]]] = None
    chat_history: List[Dict[str, Any]] = field(default_factory=list)
    pipeline_checkpoint_path: Optional[str] = None
    agents_md_content: Optional[str] = None
    summary: str = ""


class CheckpointCLI:
    """Save, load, list, and restore full session checkpoints.

    Each session is stored in a directory under DEFAULT_SESSION_ROOT.
    The directory contains structured files for each component of session
    state, plus a session.json manifest.
    """

    def __init__(self, session_root: str = DEFAULT_SESSION_ROOT):
        self._root = Path(session_root)
        self._root.mkdir(parents=True, exist_ok=True)

    # ── Directory Helpers ──────────────────────────────────────────────

    def get_session_dir(self, name: str) -> str:
        """Return the absolute path for a named session directory."""
        return str(self._root / name)

    def _session_path(self, name: str) -> Path:
        return self._root / name

    def _ensure_session_dir(self, name: str) -> Path:
        p = self._session_path(name)
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ── Save ───────────────────────────────────────────────────────────

    def save(
        self,
        session_name: str,
        pipeline: Any = None,
        cycle_count: int = 0,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        trace_history: Optional[Dict[int, Dict[str, Any]]] = None,
        agents_path: str = "AGENTS.md",
        session_essence: Optional[Dict[str, Any]] = None,
        truncated_history: Optional[List[Dict[str, Any]]] = None,
        summary: str = "",
    ) -> str:
        """Serialize full session state to a directory.

        Args:
            session_name: Directory name under session_root.
            pipeline: TelosV14Pipeline (or mock) — used to extract checkpoint ref.
            cycle_count: Current pipeline cycle number.
            chat_history: Full raw chat history.
            trace_history: Trace dicts (msg_index → trace). Not persisted directly
                           but used to derive summarized history if truncated is None.
            agents_path: Path to AGENTS.md for snapshot.
            session_essence: Dict from ContextSummarizer.get_context_block().
            truncated_history: Pre-truncated history from TokenBudgetManager.
            summary: One-line summary of what was happening.

        Returns:
            Path to the session directory.
        """
        session_dir = self._ensure_session_dir(session_name)
        chat_history = chat_history or []
        timestamp = time.time()

        # ── 1. Extract checkpoint ref from pipeline ────────────────────
        checkpoint_path: Optional[str] = None
        if pipeline is not None:
            cp = getattr(pipeline, '_checkpointer', None)
            if cp is not None:
                latest = getattr(cp, 'latest_path', None)
                if latest is not None:
                    checkpoint_path = str(latest)

        # ── 2. Snapshot AGENTS.md ──────────────────────────────────────
        agents_content: Optional[str] = None
        if os.path.exists(agents_path):
            try:
                with open(agents_path, 'r') as f:
                    agents_content = f.read()
            except OSError:
                logger.warning(f"Could not read {agents_path}")

        # ── 3. Build one-line summary if not provided ──────────────────
        if not summary:
            if session_essence:
                decisions = session_essence.get('key_decisions', [])
                intents = session_essence.get('recurring_intents', [])
                parts = []
                if decisions:
                    parts.append(f"{len(decisions)} decisions")
                if intents:
                    parts.append(f"working on: {intents[0]}")
                if parts:
                    summary = "; ".join(parts)
                else:
                    summary = f"Cycle {cycle_count} — {len(chat_history)} messages"
            else:
                summary = f"Cycle {cycle_count} — {len(chat_history)} messages"

        # ── 4. Build the checkpoint object ─────────────────────────────
        checkpoint = SessionCheckpoint(
            timestamp=timestamp,
            cycle_count=cycle_count,
            session_essence=session_essence,
            truncated_history=truncated_history,
            chat_history=chat_history,
            pipeline_checkpoint_path=checkpoint_path,
            agents_md_content=agents_content,
            summary=summary,
        )

        # ── 5. Write all files ─────────────────────────────────────────
        # session.json
        with open(session_dir / "session.json", 'w') as f:
            json.dump({
                "timestamp": checkpoint.timestamp,
                "cycle_count": checkpoint.cycle_count,
                "summary": checkpoint.summary,
                "pipeline_checkpoint_path": checkpoint.pipeline_checkpoint_path,
                "chat_history_count": len(checkpoint.chat_history),
                "truncated_history_count": len(checkpoint.truncated_history or []),
                "has_essence": checkpoint.session_essence is not None,
                "has_agents_snapshot": checkpoint.agents_md_content is not None,
            }, f, indent=2)

        # chat_history.json
        with open(session_dir / "chat_history.json", 'w') as f:
            json.dump(checkpoint.chat_history, f, indent=2, default=str)

        # truncated_history.json
        with open(session_dir / "truncated_history.json", 'w') as f:
            json.dump(checkpoint.truncated_history or [], f, indent=2, default=str)

        # essence.json
        with open(session_dir / "essence.json", 'w') as f:
            json.dump(checkpoint.session_essence or {}, f, indent=2, default=str)

        # agents.md
        if agents_content is not None:
            with open(session_dir / "agents.md", 'w') as f:
                f.write(agents_content)

        # checkpoint_ref.txt
        with open(session_dir / "checkpoint_ref.txt", 'w') as f:
            f.write(checkpoint.pipeline_checkpoint_path or "")

        logger.info(
            "Session checkpoint saved to %s — cycle %d, %d messages, %s",
            session_dir, cycle_count, len(chat_history), summary,
        )

        return str(session_dir)

    # ── Load ───────────────────────────────────────────────────────────

    def load(self, session_name: str) -> Optional[SessionCheckpoint]:
        """Deserialize a session checkpoint from its directory.

        Args:
            session_name: Directory name under session_root.

        Returns:
            SessionCheckpoint if found, else None.
        """
        session_dir = self._session_path(session_name)
        if not session_dir.exists() or not session_dir.is_dir():
            logger.warning(f"Session '{session_name}' not found at {session_dir}")
            return None

        manifest_path = session_dir / "session.json"
        if not manifest_path.exists():
            logger.warning(f"Session manifest not found: {manifest_path}")
            return None

        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read session manifest: {e}")
            return None

        # Load component files
        chat_history: List[Dict[str, Any]] = []
        chat_path = session_dir / "chat_history.json"
        if chat_path.exists():
            try:
                with open(chat_path, 'r') as f:
                    chat_history = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        truncated_history: Optional[List[Dict[str, Any]]] = None
        trunc_path = session_dir / "truncated_history.json"
        if trunc_path.exists():
            try:
                with open(trunc_path, 'r') as f:
                    truncated_history = json.load(f) or None
            except (json.JSONDecodeError, OSError):
                pass

        essence: Optional[Dict[str, Any]] = None
        essence_path = session_dir / "essence.json"
        if essence_path.exists():
            try:
                with open(essence_path, 'r') as f:
                    loaded = json.load(f) or None
                    if loaded:
                            essence = loaded
            except (json.JSONDecodeError, OSError):
                pass

        agents_content: Optional[str] = None
        agents_path = session_dir / "agents.md"
        if agents_path.exists():
            try:
                with open(agents_path, 'r') as f:
                    agents_content = f.read()
            except OSError:
                pass

        checkpoint_ref: Optional[str] = None
        ref_path = session_dir / "checkpoint_ref.txt"
        if ref_path.exists():
            try:
                with open(ref_path, 'r') as f:
                    ref = f.read().strip()
                    checkpoint_ref = ref if ref else None
            except OSError:
                pass

        return SessionCheckpoint(
            timestamp=manifest.get("timestamp", 0.0),
            cycle_count=manifest.get("cycle_count", 0),
            session_essence=essence,
            truncated_history=truncated_history,
            chat_history=chat_history,
            pipeline_checkpoint_path=checkpoint_ref,
            agents_md_content=agents_content,
            summary=manifest.get("summary", ""),
        )

    # ── List ───────────────────────────────────────────────────────────

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all saved session checkpoints.

        Returns:
            List of dicts with keys: name, timestamp, summary, cycle_count,
            chat_count, formatted_time.
        """
        results: List[Dict[str, Any]] = []
        if not self._root.exists():
            return results

        for child in sorted(self._root.iterdir()):
            if not child.is_dir():
                continue
            manifest_path = child / "session.json"
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            ts = manifest.get("timestamp", 0.0)
            formatted = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "unknown"

            results.append({
                "name": child.name,
                "timestamp": ts,
                "formatted_time": formatted,
                "summary": manifest.get("summary", ""),
                "cycle_count": manifest.get("cycle_count", 0),
                "chat_count": manifest.get("chat_history_count", 0),
            })

        # Sort by timestamp descending (most recent first)
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return results

    # ── Delete ─────────────────────────────────────────────────────────

    def delete(self, session_name: str) -> bool:
        """Delete a saved session checkpoint directory.

        Args:
            session_name: Directory name under session_root.

        Returns:
            True if deleted, False if not found.
        """
        session_dir = self._session_path(session_name)
        if not session_dir.exists():
            return False
        shutil.rmtree(session_dir)
        logger.info(f"Deleted session '{session_name}'")
        return True

    # ── Restore / Continuation Prompt ──────────────────────────────────

    def generate_continuation_prompt(
        self, session_name: str
    ) -> Optional[str]:
        """Generate a continuation prompt for restoring session context.

        This produces a markdown block that can be pasted into a new session
        to restore awareness of the previous session's state.

        Args:
            session_name: Directory name under session_root.

        Returns:
            Markdown string with restore instructions, or None if not found.
        """
        checkpoint = self.load(session_name)
        if checkpoint is None:
            return None

        # Format essence
        essence_json = json.dumps(checkpoint.session_essence or {}, indent=2)

        # Format AGENTS.md block
        agents_md = checkpoint.agents_md_content or "# No AGENTS.md snapshot\n"
        # Indent every line for blockquote display
        agents_block = "\n".join(f"> {line}" for line in agents_md.split("\n"))

        # Build checkpoint dir path
        checkpoint_dir = str(self._root)

        chat_history_path = str(self._session_path(session_name) / "chat_history.json")
        truncated_history_path = str(self._session_path(session_name) / "truncated_history.json")

        ts = datetime.fromtimestamp(checkpoint.timestamp).strftime("%Y-%m-%d %H:%M:%S")

        return CONTINUATION_PROMPT_TEMPLATE.format(
            session_name=session_name,
            timestamp=ts,
            summary=checkpoint.summary,
            checkpoint_dir=checkpoint_dir,
            agents_md_block=agents_block,
            chat_count=len(checkpoint.chat_history),
            truncated_count=len(checkpoint.truncated_history or []),
            chat_history_path=chat_history_path,
            truncated_history_path=truncated_history_path,
            essence_json=essence_json,
        )


# ── CLI Helpers ──────────────────────────────────────────────────────────
