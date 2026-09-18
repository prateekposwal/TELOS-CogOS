"""
ActionExecutor — audited real-world tool-use channel for the ACT phase.

PATTERN (audited action channel): every real-world command is
allowlist-checked, firewall-audited, operator-permitted, and trace-logged —
a block is a first-class record, never a shell pass-through.

Previously ACT could only emit synthetic vectors (`transition = np.clip(
state+action, 0, 1)`); nothing real ever happened. This executor gives ACT a
REAL channel with four hard gates, all of which must pass before any
subprocess runs:

  1. Operator permission  — a ToolPermission explicitly granted by the
     operator (PipelineConfig.operator_tool_permission) or a genuine
     HumanGateway approval this cycle. Never self-authorized.
  2. Allowlist           — the tool name must exist in ACTION_ALLOWLIST and
     every argv element must match the entry's validated template. Anything
     else is REJECTED with a block record (not allowlisted).
  3. Firewall audit      — DecisionFirewall.inspect() runs first; execution
     proceeds ONLY on verdict.passed.
  4. Bounded capture     — list-form subprocess (never shell=True), output
     capped, per-command timeout.

Every execution (allowed or blocked) produces an ActionExecution record that
the ACT phase threads into the DecisionTrace as `tool_audit` and into the
firewall's governance signals — the full command, the verdict, and the
captured result are auditable.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
import json
import numpy as np
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from telos.core.actions.registry import (
    AllowlistEntry, ToolSpec, ToolRegistry, DEFAULT_REGISTRY,
    capability_profile_for,
)
from telos.core.governance.firewall import DecisionFirewall
from telos.intent_ir import IntentIR
from telos.world.world import World

DEFAULT_OUTPUT_LIMIT = 512 * 1024   # bounded stdout/stderr capture per run
DEFAULT_TIMEOUT_SECONDS = 30.0      # per-command timeout
COMMIT_MESSAGE_LIMIT = 200          # council-approved message length cap
LOG_LIMIT_N = 30                    # git log -n bound
# Charset for council-approved commit messages (no control chars, no shell
# metacharacters — defense in depth even though we never use a shell).
_COMMIT_MESSAGE_RE = re.compile(
    r"^[A-Za-z0-9 .,:!?'()/_#@=+\-\[\]]+$"
)
# Shell metacharacters rejected in ANY argv token (defense in depth).
_SHELL_METACHARS = set(";&|$`<>()\\\n\r\t*?")

# ── Structured write-file tool bounds (governed, not freeform) ───────────────
PATCH_MAX_LINES = 200         # hard cap on old_lines/new_lines per hunk
PATCH_MAX_CHARS = 32 * 1024   # hard cap on any single hunk's content bytes
# Patch/diff/reject file extensions that are NEVER accepted as a write target:
# applying textual hunks is allowed; ingesting a pre-formed patch FILE is not
# (same rationale as rejecting shell: the write is structured & auditable).
_PATCH_FILE_EXTS = (".patch", ".diff", ".rej", ".orig")


class ToolRejected(Exception):
    """Raised when a tool request fails an allowlist/authority gate.

    Carries the block reason so the caller can produce an ActionExecution
    block record without ever executing anything.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason

def _to_text(value: Any) -> str:
    """Coerce subprocess captured bytes/str to text (bounded).

    Args:
        value: captured output (bytes, str, or None).

    Returns:
        The output as str, or "" when nothing was captured.
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)



# ── The hard allowlist (prefix-anchored argv, no shell interpretation) ──────
# The tool set is declared EXACTLY ONCE in telos/core/actions/registry.py; this
# mapping is a projection of the canonical ToolRegistry so the executor, the
# audit tooling, and the documentation can never drift apart. Every entry is a
# ToolSpec (alias AllowlistEntry) with an argv template, kind, description, and
# family.
ACTION_ALLOWLIST: Dict[str, AllowlistEntry] = DEFAULT_REGISTRY.as_allowlist()


# Network URL/tool bounds (validated before any socket opens).
MAX_URL_CHARS = 2048


def _validate_url(value: str) -> str:
    """Validate an {url} placeholder for the governed network tools.

    Args:
        value: the raw URL candidate.

    Returns:
        The validated URL, or raises ToolRejected.
    """
    if not isinstance(value, str) or not value.strip():
        raise ToolRejected("network tool requires a non-empty url")
    if len(value) > MAX_URL_CHARS:
        raise ToolRejected(f"url exceeds {MAX_URL_CHARS} chars")
    # Defense in depth: no whitespace/control chars, and an explicit scheme.
    if any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise ToolRejected("url contains whitespace/control characters")
    if not (value.startswith("https://") or value.startswith("http://")):
        raise ToolRejected("url must be absolute (https:// or http://)")
    return value


def _validate_n(value: str) -> str:
    """Validate the {n} placeholder as an integer in 1..LOG_LIMIT_N.

    Args:
        value: the raw substitution candidate.

    Returns:
        The validated string, or raises ToolRejected.
    """
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ToolRejected(f"git_log count {value!r} is not an integer")
    if not 1 <= n <= LOG_LIMIT_N:
        raise ToolRejected(f"git_log count {n} outside 1..{LOG_LIMIT_N}")
    return str(n)


def _resolve_inside(base: str, candidate: str) -> str:
    """Resolve a path and require it to live inside the operator's workspace.

    Args:
        base: the workspace root (Path containment anchor).
        candidate: the raw path to validate.

    Returns:
        The resolved absolute path, or raises ToolRejected.

    Raises:
        ToolRejected: when the path does not resolve inside the workspace.
    """
    base_path = Path(base).resolve()
    raw = Path(candidate)
    cand_path = (base_path / raw).resolve() if not raw.is_absolute() else raw.resolve()
    try:
        cand_path.relative_to(base_path)
    except ValueError:
        raise ToolRejected(
            f"path {str(cand_path)!r} is outside the workspace root {str(base_path)!r}"
        )
    return str(cand_path)


def _validate_message(value: str) -> str:
    """Validate the {message} placeholder (council-approved commit message).

    Args:
        value: the raw message candidate.

    Returns:
        The validated message, or raises ToolRejected.
    """
    if not value or not value.strip():
        raise ToolRejected("empty commit message")
    if len(value) > COMMIT_MESSAGE_LIMIT:
        raise ToolRejected(
            f"commit message exceeds {COMMIT_MESSAGE_LIMIT} chars"
        )
    if not _COMMIT_MESSAGE_RE.match(value):
        raise ToolRejected("commit message contains unapproved characters")
    return value


def _validate_argv_token(token: str) -> str:
    """Reject shell metacharacters in ANY argv token (defense in depth).

    Args:
        token: a single argv element.

    Returns:
        The token unchanged, or raises ToolRejected.
    """
    if any(ch in _SHELL_METACHARS for ch in token):
        raise ToolRejected(f"argv token contains shell metacharacter: {token!r}")
    return token


# Make target name: a bare identifier (letters/digits/-/_), never freeform.
_MAKE_TARGET_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _validate_target(value: str) -> str:
    """Validate a make target name (no separators, slashes, or shell).

    Args:
        value: the raw target candidate.

    Returns:
        The validated target, or raises ToolRejected.
    """
    if not value or not value.strip():
        raise ToolRejected("empty make target")
    if not _MAKE_TARGET_RE.match(value):
        raise ToolRejected(
            f"make target {value!r} contains unapproved characters"
        )
    if any(ch in _SHELL_METACHARS for ch in value):
        raise ToolRejected(f"make target contains shell metacharacter: {value!r}")
    return value


def _validate_cwd_inside(base: str, cwd: Optional[str]) -> Optional[str]:
    """Require a supplied subprocess cwd to resolve INSIDE the workspace.

    Every toolchain command (tsc/eslint/npm/make/go) runs in a governed cwd;
    an operator may point it at a workspace subdirectory but never outside it.

    Args:
        base: the workspace root (path containment anchor).
        cwd: the requested working directory (None = default workspace root).

    Returns:
        The validated absolute cwd, or raises ToolRejected.
    """
    if cwd is None:
        return str(Path(base).resolve())
    base_path = Path(base).resolve()
    raw = Path(cwd)
    cand = (base_path / raw).resolve() if not raw.is_absolute() else raw.resolve()
    try:
        cand.relative_to(base_path)
    except ValueError:
        raise ToolRejected(
            f"cwd {str(cand)!r} is outside the workspace root {str(base_path)!r}"
        )
    return str(cand)


@dataclass
class ToolPermission:
    """An operator/HumanGateway-granted request to run ONE allowlisted tool.

    permitted_by: "operator" (PipelineConfig.operator_tool_permission) or
        "human_gateway" (a genuine HumanGateway approval this cycle).
    args: the concrete argv that will be validated against the allowlist
        template (placeholders like {n}, {path}, {message} are expanded from
        args[1:] in template order).
    cwd: working directory for the command (defaults to executor workspace).
    approved_message: the council-approved commit message for git_commit.
    permission_id: optional audit id linking the request to its approval.
    """
    tool_name: str
    args: List[str] = field(default_factory=list)
    cwd: Optional[str] = None
    permitted_by: str = "operator"
    approved_message: Optional[str] = None
    permission_id: Optional[str] = None
    # Structured write-file patch (only for the write_file tool). Carried in
    # args[0] as a dict; validated into a PatchSpec during build_argv and
    # applied by the structured-write executor path (never a subprocess).
    patch: Optional[Dict[str, Any]] = None
    # Transient: the validated PatchSpec produced by build_argv for write_file.
    _validated_patch: Any = field(default=None, repr=False, compare=False)
    # Transient: the validated (contained) cwd produced by build_argv.
    _validated_cwd: Any = field(default=None, repr=False, compare=False)
    # Transient: the validated URL produced by build_argv (network tools).
    _validated_url: Any = field(default=None, repr=False, compare=False)
    # Transient: the validated request body produced by build_argv.
    _validated_body: Any = field(default=None, repr=False, compare=False)


@dataclass
class PatchSpec:
    """A structured, minimal, auditable file write (never freeform shell).

    Corresponds to the `write_file` allowlist tool. A PatchSpec replaces ONE
    contiguous block of an EXISTING TRACKED file inside the workspace root:
      - path: workspace-relative or absolute path to the file to write.
      - old_lines: the exact contiguous lines currently in the file that are
        to be replaced (must match EXACTLY ONCE — ambiguity is rejected).
      - new_lines: the replacement lines (bounded size).
    Validation rejects: unknown paths, patch/diff file targets, a block that
    is not found exactly once, oversized hunks, and any non-dict spec.
    """
    path: str
    old_lines: List[str] = field(default_factory=list)
    new_lines: List[str] = field(default_factory=list)


def _validate_patch_spec(raw: Any, workspace_root: str) -> PatchSpec:
    """Validate a structured patch dictionary against the write-file gates.

    Args:
        raw: the submitted patch object (must be a dict with path/old_lines/
            new_lines).
        workspace_root: the operator-granted workspace root (path containment).

    Returns:
        A validated PatchSpec ready for application.

    Raises:
        ToolRejected: on ANY gate failure (not a dict / bad shape / path
            escape / patch-file target / block not found / over-bounded).
    """
    if not isinstance(raw, dict):
        raise ToolRejected("write_file patch must be a structured dict, not freeform text")
    path_val = raw.get("path")
    old_lines = raw.get("old_lines") or []
    new_lines = raw.get("new_lines") or []
    if not isinstance(path_val, str) or not path_val.strip():
        raise ToolRejected("write_file patch requires a non-empty 'path'")
    if not isinstance(old_lines, list) or not isinstance(new_lines, list):
        raise ToolRejected("write_file patch old_lines/new_lines must be lists")
    # Path containment + must be an EXISTING regular file.
    resolved = _resolve_inside(workspace_root, path_val)
    # Reject patch/diff file targets outright.
    if resolved.lower().endswith(_PATCH_FILE_EXTS):
        raise ToolRejected(
            f"refusing to write a patch/diff file target: {resolved!r}"
        )
    # The write target must already exist as a tracked regular file (a write
    # against a path that does not exist is rejected — no arbitrary file
    # creation through the governed channel).
    try:
        if not os.path.isfile(resolved):
            raise ToolRejected(f"write_file target is not an existing file: {resolved!r}")
    except OSError:
        raise ToolRejected(f"cannot stat write_file target: {resolved!r}")
    # Hard bounds on hunk size.
    if not old_lines:
        raise ToolRejected("write_file requires non-empty old_lines to replace")
    if len(old_lines) > PATCH_MAX_LINES or len(new_lines) > PATCH_MAX_LINES:
        raise ToolRejected(
            f"write_file hunk exceeds {PATCH_MAX_LINES} lines (got "
            f"{len(old_lines)} old / {len(new_lines)} new)"
        )
    if sum(len(l) for l in old_lines) + sum(len(l) for l in new_lines) > PATCH_MAX_CHARS:
        raise ToolRejected(f"write_file hunk exceeds {PATCH_MAX_CHARS} content chars")
    # Normalize line endings (hunks use newline; tolerate CRLF).
    def _norm(lines: List[str]) -> List[str]:
        return [l.rstrip("\r") for l in lines]
    spec = PatchSpec(
        path=resolved,
        old_lines=_norm(list(old_lines)),
        new_lines=_norm(list(new_lines)),
    )
    # Exact-once match must hold (ambiguity or absence is rejected BEFORE any write).
    try:
        text = open(spec.path, "r", encoding="utf-8", errors="replace").read()
    except OSError as e:
        raise ToolRejected(f"cannot read write_file target for match check: {e}")
    content_lines = text.split("\n")
    match_count = _count_block_occurrences(content_lines, spec.old_lines)
    if match_count == 0:
        raise ToolRejected("write_file old_lines block not found in target (no-op rejected)")
    if match_count > 1:
        raise ToolRejected(
            f"write_file old_lines block matches {match_count} times (ambiguous; "
            "refusing the write)"
        )
    return spec


def _count_block_occurrences(content_lines: List[str], block: List[str]) -> int:
    """Count non-overlapping exact occurrences of `block` within content_lines.

    Args:
        content_lines: the file's lines (without trailing newlines).
        block: the exact old_lines block to locate.

    Returns:
        The number of exact contiguous matches in content_lines.
    """
    n = len(block)
    if n == 0:
        return 0
    count = 0
    i = 0
    while i <= len(content_lines) - n:
        if content_lines[i:i + n] == block:
            count += 1
            i += n
        else:
            i += 1
    return count


@dataclass
class ActionExecution:
    """The audited record of one tool request — allowed OR blocked.

    Every field is real: command is the exact argv that ran (or would have
    run), blocked_reason names the failing gate when nothing ran, and
    stdout/stderr are the bounded captured outputs.
    """
    tool_name: str
    command: str
    allowed: bool
    blocked_reason: Optional[str] = None
    firewall_verdict: Optional[Dict[str, Any]] = None
    returncode: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_ms: float = 0.0
    executed_at: float = 0.0
    permission_id: Optional[str] = None
    permitted_by: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serializable audit record for the DecisionTrace tool_audit field."""
        return {
            "tool_name": self.tool_name,
            "command": self.command,
            "allowed": self.allowed,
            "blocked_reason": self.blocked_reason,
            "firewall_verdict": self.firewall_verdict,
            "returncode": self.returncode,
            "stdout": self.stdout[:4000],
            "stderr": self.stderr[:2000],
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
            "executed_at": self.executed_at,
            "permission_id": self.permission_id,
            "permitted_by": self.permitted_by,
        }


def _find_block_index(content_lines: List[str], block: List[str]) -> Optional[int]:
    """Return the index of the unique exact block match (or None).

    Args:
        content_lines: the file's lines (no trailing newline per line).
        block: the old_lines block to locate.

    Returns:
        The start index if the block appears exactly once, else None (the
        caller's validation already rejected ambiguous/absent blocks).
    """
    n = len(block)
    if n == 0:
        return None
    for i in range(len(content_lines) - n + 1):
        if content_lines[i:i + n] == block:
            return i
    return None


class ActionExecutor:
    """Executes operator-permitted, allowlisted, firewall-audited commands.

    The executor is a HARD gate, not a convenience wrapper: every request
    travels through permission -> allowlist -> firewall -> bounded subprocess,
    and every outcome (including every block) is returned as an
    ActionExecution audit record for the decision trace.
    """

    def __init__(self, workspace_root: str,
                 allowlist: Optional[Dict[str, AllowlistEntry]] = None,
                 output_limit: int = DEFAULT_OUTPUT_LIMIT,
                 timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 sandbox: Any = None):
        """Construct an executor bound to one operator workspace.

        Args:
            workspace_root: the ONLY directory tree this executor may touch
                (path containment for {path} placeholders and default cwd).
            allowlist: optional override of the global ACTION_ALLOWLIST.
            output_limit: bounded stdout/stderr capture per command in bytes.
            timeout: per-command timeout in seconds.
            sandbox: optional NetworkSandbox for the network tool family
                (created lazily on first network tool use when None).
        """
        self.workspace_root = str(Path(workspace_root).resolve())
        self.allowlist = dict(ACTION_ALLOWLIST if allowlist is None else allowlist)
        self.output_limit = int(output_limit)
        self.timeout = float(timeout)
        self._sandbox = sandbox

    def _capability_gate(self, tool_name: str,
                         capability: Any) -> Optional[Dict[str, Any]]:
        """Per-tool capability authorization (Phase 1).

        The registry declares which CapabilityAuthorization gates a tool
        requires (by kind, or its explicit profile). This gate vetoes the tool
        exactly as the council vetoes an action: a FAIL on any required gate is
        a hard, non-tradeable block.

        Args:
            tool_name: the tool being requested.
            capability: a CapabilityAuthorization (or any object exposing
                ``gate(name)``), or None to skip the gate.

        Returns:
            A verdict dict when the gate ran and passed, else None (skip).

        Raises:
            ToolRejected: when a required capability gate is FAIL.
        """
        if capability is None:
            return None
        spec = self.allowlist.get(tool_name)
        if spec is None:
            return None
        required = capability_profile_for(spec)
        failed = []
        checked = {}
        for gate_name in required:
            gate = capability.gate(gate_name) if hasattr(capability, "gate") else None
            status = getattr(getattr(gate, "status", None), "value", None)
            checked[gate_name] = status or "UNKNOWN"
            if status == "FAIL":
                failed.append(gate_name)
        if failed:
            raise ToolRejected(
                f"capability gate vetoed tool {tool_name!r}: "
                f"failed {'/'.join(failed)}"
            )
        return {"tool": tool_name, "required": required, "observed": checked}

    def build_argv(self, permission: ToolPermission) -> List[str]:
        """Validate a permission against the allowlist and build the argv.

        Args:
            permission: the operator-granted tool request to validate.

        Returns:
            The validated argv (list-form, never shell-interpreted).

        Raises:
            ToolRejected: on ANY gate failure (unknown tool / bad placeholder /
                bad args count / path escape / metacharacter).
        """
        entry = self.allowlist.get(permission.tool_name)
        if entry is None:
            raise ToolRejected(
                f"tool {permission.tool_name!r} is not on the allowlist"
            )
        if permission.permitted_by not in ("operator", "human_gateway"):
            raise ToolRejected(
                f"permission source {permission.permitted_by!r} is not a "
                "recognized authorizer (operator or human_gateway)"
            )
        template = list(entry.template)
        # Expand placeholders in template order from the permission args.
        supplied = list(permission.args or [])
        for idx, piece in enumerate(template):
            if piece.startswith("{") and piece.endswith("}"):
                ph = piece[1:-1]
                if not supplied:
                    raise ToolRejected(
                        f"missing argument for placeholder {{{ph}}} in "
                        f"{permission.tool_name}"
                    )
                raw = supplied.pop(0)
                if ph == "n":
                    template[idx] = _validate_n(raw)
                elif ph == "path":
                    template[idx] = _resolve_inside(self.workspace_root, raw)
                elif ph == "message":
                    msg = raw if raw else (permission.approved_message or "")
                    template[idx] = _validate_message(msg)
                elif ph == "target":
                    template[idx] = _validate_target(str(raw))
                elif ph == "url":
                    template[idx] = _validate_url(str(raw))
                    permission._validated_url = template[idx]
                elif ph == "body":
                    body_str = raw if isinstance(raw, str) else json.dumps(raw)
                    if len(body_str.encode("utf-8")) > 256 * 1024:
                        raise ToolRejected("network request body exceeds 262144 bytes")
                    template[idx] = body_str
                    permission._validated_body = body_str
                elif ph == "patch":
                    # write_file carries a structured patch dict (args[0]).
                    # Parse JSON if the caller passed a string; accept a dict.
                    raw_patch = raw
                    if isinstance(raw_patch, str):
                        try:
                            import json
                            raw_patch = json.loads(raw_patch)
                        except Exception:
                            raise ToolRejected(
                                "write_file patch must be a structured dict or valid JSON"
                            )
                    spec = _validate_patch_spec(raw_patch, self.workspace_root)
                    permission._validated_patch = spec
                    # Display descriptor only (never a real argv); kept free of
                    # shell metacharacters so the defense-in-depth token check
                    # does not reject it.
                    template[idx] = (
                        f"write_file {spec.path} "
                        f"replace-{len(spec.old_lines)}L add-{len(spec.new_lines)}L"
                    )
                else:
                    raise ToolRejected(f"unknown placeholder {{{ph}}} in allowlist")
        if supplied:
            raise ToolRejected(
                f"too many args for {permission.tool_name}: extra {supplied!r}"
            )
        for tok in template:
            _validate_argv_token(tok)
        # Any supplied cwd must be INSIDE the workspace (toolchain commands run
        # in a governed directory — never outside it).
        worked = _validate_cwd_inside(self.workspace_root, permission.cwd)
        permission._validated_cwd = worked
        return template

    def _firewall_audit(self, firewall: Optional[DecisionFirewall],
                        tool_name: str) -> Optional[Dict[str, Any]]:
        """Run DecisionFirewall.inspect(); only a passed verdict may proceed.

        Args:
            firewall: the DecisionFirewall to audit through (None blocks).
            tool_name: the allowlisted tool being requested.

        Returns:
            The verdict dict if the audit PASSED, else None (caller blocks).

        Raises:
            ToolRejected: when no firewall is provided, or the firewall blocks.
        """
        if firewall is None:
            raise ToolRejected("no DecisionFirewall available for the tool audit")
        world = World(
            state=np.zeros(1),
            metadata={"tool": tool_name, "domain": "gitrepo"},
        )
        intent = IntentIR(
            intent_type=f"tool_execute:{tool_name}",
            confidence=1.0,
            params={"tool_name": tool_name},
        )
        verdict = firewall.inspect(
            world, intent,
            council_validated=True,
            decision_integrity=1.0,
            domain="gitrepo",
        )
        verdict_dict = {
            "passed": verdict.passed,
            "reason": verdict.reason,
            "blocked_by": verdict.blocked_by,
            "governance_signals": verdict.governance_signals,
        }
        if not verdict.passed:
            raise ToolRejected(f"firewall blocked tool: {verdict.reason}")
        return verdict_dict

    def execute(self, permission: ToolPermission,
                firewall: Optional[DecisionFirewall] = None,
                capability: Any = None) -> ActionExecution:
        """Run the full gate sequence; return the audited outcome.

        Args:
            permission: the operator-granted tool request.
            firewall: the DecisionFirewall to audit through (REQUIRED for
                execution — a missing firewall is itself a block).
            capability: optional CapabilityAuthorization for the per-tool
                capability gate (Phase 1). None skips the gate (pre-Phase-1
                behavior); a FAIL on a required gate vetoes the tool.

        Returns:
            ActionExecution audit record: allowed=True only when every gate
            passed and the subprocess ran; every other path is a block record.
        """
        executed_at = time.time()
        started = time.monotonic()
        record = ActionExecution(
            tool_name=permission.tool_name,
            command="", allowed=False, executed_at=executed_at,
            permission_id=permission.permission_id,
            permitted_by=permission.permitted_by or "",
        )
        try:
            argv = self.build_argv(permission)
            record.command = " ".join(shlex.quote(a) for a in argv)
            cap_verdict = self._capability_gate(permission.tool_name, capability)
            verdict = self._firewall_audit(firewall, permission.tool_name)
            if cap_verdict is not None:
                verdict = dict(verdict or {})
                verdict["capability_gate"] = cap_verdict
            record.firewall_verdict = verdict
            entry_kind = self.allowlist[permission.tool_name].kind
        except ToolRejected as e:
            record.blocked_reason = e.reason
            record.duration_ms = (time.monotonic() - started) * 1000.0
            return record

        # Structured write-file tools do NOT spawn a subprocess: they apply a
        # validated patch to a file directly (governed + audited, never shell).
        if entry_kind == "structured_write":
            return self._execute_structured_write(permission, record, started)

        # Network tools do NOT spawn a subprocess either: they leave ONLY via
        # the governed NetworkSandbox (host/port/route allowlist + bounds).
        if entry_kind in ("network_read", "network_write") \
                or self.allowlist[permission.tool_name].family in ("network_read", "network_write"):
            return self._execute_network(permission, record, started)

        try:
            proc = subprocess.run(
                argv,
                cwd=getattr(permission, '_validated_cwd', None)
                or self.workspace_root,
                capture_output=True, text=True, timeout=self.timeout,
            )
            record.returncode = proc.returncode
            record.stdout = proc.stdout[:self.output_limit]
            record.stderr = proc.stderr[:self.output_limit]
        except subprocess.TimeoutExpired as e:
            record.timed_out = True
            record.stdout = _to_text(e.stdout)[:self.output_limit]
            record.stderr = _to_text(e.stderr)[:self.output_limit]
        except Exception as e:
            record.blocked_reason = f"execution error: {e}"
            record.duration_ms = (time.monotonic() - started) * 1000.0
            return record

        record.allowed = True
        record.duration_ms = (time.monotonic() - started) * 1000.0
        return record

    def _execute_network(self, permission: ToolPermission,
                         record: ActionExecution,
                         started: float) -> ActionExecution:
        """Perform a governed network request through the NetworkSandbox.

        The sandbox is the ONLY egress channel: it re-validates host/port/route
        against its own allowlist and bounds the payloads. A sandbox refusal is
        a block record (nothing left the process).

        Args:
            permission: the network tool request (its _validated_url/_body were
                set during build_argv).
            record: the in-progress ActionExecution audit record.
            started: monotonic start time for duration accounting.

        Returns:
            The final ActionExecution: allowed=True only on a real response.
        """
        url = getattr(permission, '_validated_url', None)
        body = getattr(permission, '_validated_body', None) or ""
        if not url:
            record.blocked_reason = "network tool validated url missing (governance_blocked_cycle)"
            record.duration_ms = (time.monotonic() - started) * 1000.0
            return record
        if self._sandbox is None:
            from telos.core.actions.sandbox import NetworkSandbox
            self._sandbox = NetworkSandbox(timeout=self.timeout)
        method = "GET" if permission.tool_name == "http_get" else "POST"
        result = self._sandbox.request(method, url, body=body)
        record.returncode = result.status if result.status is not None else None
        if result.allowed:
            record.allowed = True
            record.stdout = result.body[:self.output_limit]
        else:
            record.blocked_reason = result.blocked_reason
        record.duration_ms = (time.monotonic() - started) * 1000.0
        return record

    def _execute_structured_write(self, permission: ToolPermission,
                                  record: ActionExecution,
                                  started: float) -> ActionExecution:
        """Apply a validated write_file patch to the target file (no subprocess).

        A structured write is still fully audited: it records a block
        (firewall/validation ran earlier) unless the patch applies cleanly on
        an EXACT-ONCE match. The write is atomic (temp file + os.replace) so a
        failed write never leaves a half-applied file. The unified diff that
        the write produced is captured in record.stdout for the trace.

        Args:
            permission: the operator-granted write_file request (its
                _validated_patch was set during build_argv).
            record: the in-progress ActionExecution audit record.
            started: monotonic start time for duration accounting.

        Returns:
            The final ActionExecution: allowed=True only if the file changed.
        """
        spec = getattr(permission, '_validated_patch', None)
        if spec is None:
            record.blocked_reason = "write_file validated patch missing (governance_blocked_cycle)"
            record.duration_ms = (time.monotonic() - started) * 1000.0
            return record
        try:
            text = open(spec.path, "r", encoding="utf-8", errors="replace").read()
            content_lines = text.split("\n")
            # Preserve whether the original ended with a newline.
            had_trailing_nl = text.endswith("\n")
            n = len(spec.old_lines)
            idx = _find_block_index(content_lines, spec.old_lines)
            if idx is None:
                record.blocked_reason = "write_file block no longer present (writes nothing)"
                record.duration_ms = (time.monotonic() - started) * 1000.0
                return record
            new_content_lines = (
                content_lines[:idx] + list(spec.new_lines) + content_lines[idx + n:]
            )
            new_text = "\n".join(new_content_lines)
            if had_trailing_nl and not new_text.endswith("\n"):
                new_text += "\n"
            if new_text == text:
                record.blocked_reason = "write_file produced no change (no-op rejected)"
                record.duration_ms = (time.monotonic() - started) * 1000.0
                return record
            # Atomic write: temp file in same dir, then os.replace.
            import tempfile
            d = os.path.dirname(spec.path) or "."
            fd, tmp_path = tempfile.mkstemp(dir=d, prefix=".telos_write_", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(new_text)
                os.replace(tmp_path, spec.path)
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
        except OSError as e:
            record.blocked_reason = f"write_file io error: {e}"
            record.duration_ms = (time.monotonic() - started) * 1000.0
            return record
        # Capture a unified-style diff summary of exactly what changed.
        removed = len(spec.old_lines)
        added = len(spec.new_lines)
        record.stdout = (
            f"applied write_file to {spec.path}: -{removed}/+{added} lines\n"
            + "\n".join(f"+ {l}" for l in spec.new_lines[:30])
        )
        record.returncode = 0
        record.allowed = True
        record.duration_ms = (time.monotonic() - started) * 1000.0
        return record


    def audit_entry(self, execution: ActionExecution) -> Dict[str, Any]:
        """A compact governance-signal entry for the firewall's signal list.

        Args:
            execution: the ActionExecution record to summarize.

        Returns:
            Dict suitable for appending to governance_signals in a trace.
        """
        return {
            "check": "tool_audit",
            "passed": execution.allowed,
            "tool": execution.tool_name,
            "command": execution.command,
            "blocked_reason": execution.blocked_reason,
            "returncode": execution.returncode,
            "stdout_tail": execution.stdout[-400:],
            "permitted_by": execution.permitted_by,
        }


__all__ = [
    "ACTION_ALLOWLIST", "AllowlistEntry", "ToolSpec", "ToolRegistry",
    "ToolPermission", "ActionExecution",
    "ActionExecutor", "ToolRejected",
]