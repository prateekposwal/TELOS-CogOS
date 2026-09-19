"""
WorldAdapter — the ONE canonical contract for a real-world action capability.

PATTERN (one governed real-world action path): the audited ActionExecutor is
the execution substrate and the NetworkSandbox is the network substrate; a
WorldAdapter is the *typed capability* that sits above them. It answers four
questions, in order, for exactly one capability name:

    observe()          -> what is the real-world state right now?
    validate_action()  -> is this action well-formed and permitted here?
    execute()          -> perform the action (through the governed executor)
    verify_result()    -> did the observed result match the prediction?

An adapter NEVER opens its own subprocess, socket, or file write. Its
``execute`` delegates to the injected ActionExecutor (the allowlist + firewall
+ operator-permission + rate-limit gates still apply, unchanged), and its
``validate_action`` reuses the executor's own ``build_argv`` so there is no
parallel ungoverned path and no second place validation can drift.

Capability names: each adapter declares a ``capability_name`` (e.g.
``"filesystem.write"``). Authorization is PER CAPABILITY — the certification
registry and the capability-authorization gates are keyed on that name, so
certifying/authorizing one capability says nothing about any other. There is no
adapter -> no action: an unconfigured capability or a mismatched adapter
refuses rather than falling through to anything.

This module is item 3 of the real-world action path; the dry-run/LIVE runners
(item 4/5) live in ``world_action.py``. Items 6-10 (post-action observation,
Reality-Gap measurement, authority recalibration, per-capability certification
workflow) attach at the ``verify_result`` / runner seams without changing this
contract.
"""

from __future__ import annotations

import shlex
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional

from telos.core.actions.executor import (
    ActionExecution, ActionExecutor, ToolPermission, ToolRejected,
)
from telos.core.actions.registry import capability_profile_for

# Read bound for observe() snapshots (never read an unbounded file into memory).
DEFAULT_OBSERVE_CHARS = 64 * 1024


@dataclass
class WorldObservation:
    """A real-world state snapshot taken by an adapter.

    Attributes:
        source: where the observation came from (e.g. ``"file:notes.md"``).
        state: a JSON-serializable snapshot (adapter-specific shape).
        captured_at: wall-clock epoch of the observation (this channel is
            opt-in and never part of the deterministic core).
        metadata: optional adapter-specific annotations.
    """

    source: str
    state: Any = None
    captured_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializable observation record.

        Returns:
            Dict of source/state/metadata (captured_at retained).
        """
        return {
            "source": self.source,
            "state": self.state,
            "captured_at": self.captured_at,
            "metadata": dict(self.metadata),
        }


@dataclass
class ValidationResult:
    """The outcome of validating one proposed action for an adapter.

    Attributes:
        valid: True when the action is well-formed and permitted for this
            adapter (it would be accepted by the governed executor).
        reason: the recorded reason when invalid, else "ok".
        command: the would-be command/action string when valid.
    """

    valid: bool
    reason: str = ""
    command: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serializable validation record.

        Returns:
            Dict of valid/reason/command.
        """
        return {"valid": self.valid, "reason": self.reason,
                "command": self.command}


@dataclass
class VerificationResult:
    """The comparison of a prediction against a later observation.

    Attributes:
        matched: True when the observation matched the prediction.
        reality_gap: a 0..1 gap (0.0 = exact match, 1.0 = no match).
        predicted: the predicted result that was compared.
        observed: the observed result that was compared.
        detail: a human-readable explanation of the comparison.
    """

    matched: bool
    reality_gap: float
    predicted: Any = None
    observed: Any = None
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serializable verification record.

        Returns:
            Dict of matched/reality_gap/predicted/observed/detail.
        """
        return {
            "matched": self.matched,
            "reality_gap": self.reality_gap,
            "predicted": self.predicted,
            "observed": self.observed,
            "detail": self.detail,
        }


class AdapterRefused(Exception):
    """Raised when an adapter refuses an action (nothing is executed)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class WorldAdapter(ABC):
    """The canonical real-world action contract (one capability per adapter).

    Concrete adapters declare a capability name, an operation name, and the
    underlying governed tool. ``validate_action`` and ``execute`` are provided
    by the base and delegate to the injected ActionExecutor; subclasses supply
    ``observe``, ``build_permission``, and ``verify_result``.
    """

    #: The capability name this adapter realizes (authorization is per-name).
    capability_name: ClassVar[str] = ""
    #: The operation name this adapter performs (e.g. the tool family verb).
    operation_name: ClassVar[str] = ""
    #: The governed tool name this adapter executes through.
    tool_name: ClassVar[str] = ""

    def __init__(self, executor: ActionExecutor):
        """Bind the adapter to its execution substrate.

        Args:
            executor: the audited ActionExecutor this adapter executes through.
        """
        self.executor = executor

    @abstractmethod
    def observe(self) -> WorldObservation:
        """Read the real-world state this adapter acts upon (no effect).

        Returns:
            The current WorldObservation.
        """
        raise NotImplementedError

    @abstractmethod
    def build_permission(self, proposal: Any,
                         permitted_by: str = "operator") -> ToolPermission:
        """Translate a proposal into the governed ToolPermission to execute.

        Args:
            proposal: the WorldActionProposal to translate.
            permitted_by: the authorization source ("operator" / "human_gateway").

        Returns:
            The ToolPermission the executor will validate and (in LIVE) run.
        """
        raise NotImplementedError

    @abstractmethod
    def verify_result(self, prediction: Any,
                      observation: WorldObservation) -> VerificationResult:
        """Compare a prediction against a later observation.

        Args:
            prediction: the predicted result to compare.
            observation: the later observation to compare against.

        Returns:
            The VerificationResult (matched + reality gap).
        """
        raise NotImplementedError

    def validate_action(self, proposal: Any) -> ValidationResult:
        """Validate a proposal against this adapter and the governed allowlist.

        Reuses the executor's own ``build_argv`` (allowlist membership,
        template/placeholder validation, path containment) — there is no second
        validation implementation to drift.

        Args:
            proposal: the WorldActionProposal to validate.

        Returns:
            ValidationResult (valid + the would-be command, or a reason).
        """
        if proposal.capability and proposal.capability != self.capability_name:
            return ValidationResult(
                valid=False,
                reason=(f"capability mismatch: proposal declares "
                        f"{proposal.capability!r} but adapter realizes "
                        f"{self.capability_name!r}"),
            )
        if proposal.operation and proposal.operation != self.operation_name:
            return ValidationResult(
                valid=False,
                reason=(f"operation mismatch: proposal declares "
                        f"{proposal.operation!r} but adapter performs "
                        f"{self.operation_name!r}"),
            )
        try:
            permission = self.build_permission(proposal, permitted_by="operator")
            argv = self.executor.build_argv(permission)
        except ToolRejected as e:
            return ValidationResult(valid=False, reason=e.reason)
        return ValidationResult(
            valid=True, reason="ok",
            command=" ".join(shlex.quote(a) for a in argv),
        )

    def execute(self, proposal: Any, *, firewall: Any,
                capability: Any = None,
                permitted_by: str = "operator") -> ActionExecution:
        """Execute a proposal through the governed executor.

        The executor re-runs the whole gate chain (allowlist/template, firewall
        audit, operator permission, rate limit); this adapter adds no path of
        its own.

        Args:
            proposal: the WorldActionProposal to execute.
            firewall: the DecisionFirewall the executor audits through
                (required — a missing firewall is itself a block).
            capability: optional CapabilityAuthorization for the per-tool gate.
            permitted_by: the authorization source ("operator" / "human_gateway").

        Returns:
            The ActionExecution audit record (allowed OR a block record).
        """
        permission = self.build_permission(proposal, permitted_by=permitted_by)
        return self.executor.execute(permission, firewall=firewall,
                                     capability=capability)

    def required_gates(self) -> List[str]:
        """The capability-authorization gates this adapter's tool requires.

        Returns:
            List of gate names drawn from the canonical registry profile.
        """
        spec = self.executor.allowlist.get(self.tool_name)
        if spec is None:
            return []
        return list(capability_profile_for(spec))

    def descriptor(self) -> Dict[str, Any]:
        """A compact description of the adapter's identity (audit/trace).

        Returns:
            Dict with capability/operation/tool/workspace.
        """
        return {
            "capability": self.capability_name,
            "operation": self.operation_name,
            "tool": self.tool_name,
            "workspace_root": self.executor.workspace_root,
            "required_gates": self.required_gates(),
        }


class FilesystemWriteAdapter(WorldAdapter):
    """A concrete, sandbox-confined filesystem-write capability.

    Realizes ``capability_name="filesystem.write"`` over the governed
    ``write_file`` tool: a structured, minimal, exact-once block replacement
    inside the operator's tool workspace. It never accepts freeform text and
    never writes outside the workspace (the executor's containment gate), so
    the capability is harmless to anything the operator did not explicitly
    grant. ``observe`` reads the target file (bounded); ``verify_result``
    compares the observed content against the predicted content.
    """

    capability_name = "filesystem.write"
    operation_name = "write_file"
    tool_name = "write_file"

    def __init__(self, executor: ActionExecutor, target: str,
                 observe_chars: int = DEFAULT_OBSERVE_CHARS):
        """Bind the adapter to one target file inside the workspace.

        Args:
            executor: the governed ActionExecutor (workspace root = sandbox).
            target: the target file path (workspace-relative or absolute
                inside the workspace) this adapter observes and writes.
            observe_chars: read bound for observe() content snapshots.
        """
        super().__init__(executor)
        self.target = target
        self.observe_chars = int(observe_chars)

    def _resolved_target(self) -> Path:
        """Resolve the bound target strictly inside the workspace root.

        Returns:
            The resolved target path.
        """
        base = Path(self.executor.workspace_root).resolve()
        raw = Path(self.target)
        return (base / raw).resolve() if not raw.is_absolute() else raw.resolve()

    def observe(self) -> WorldObservation:
        """Read the target file's current content (bounded, never writes).

        Returns:
            A WorldObservation whose state carries the content (or an
            ``exists=False`` marker when the target is absent).
        """
        import time
        path = self._resolved_target()
        base = Path(self.executor.workspace_root).resolve()
        inside = True
        try:
            path.relative_to(base)
        except ValueError:
            inside = False
        if not inside:
            return WorldObservation(
                source=f"file:{self.target}", state={"exists": False},
                captured_at=time.time(),
                metadata={"blocked": "target_outside_workspace"},
            )
        if not path.is_file():
            return WorldObservation(
                source=f"file:{self.target}", state={"exists": False},
                captured_at=time.time(),
            )
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return WorldObservation(
                source=f"file:{self.target}", state={"exists": False},
                captured_at=time.time(),
                metadata={"read_error": str(e)},
            )
        return WorldObservation(
            source=f"file:{self.target}",
            state={"exists": True, "content": content[:self.observe_chars]},
            captured_at=time.time(),
            metadata={"chars": len(content), "truncated": len(content) > self.observe_chars},
        )

    def build_permission(self, proposal: Any,
                         permitted_by: str = "operator") -> ToolPermission:
        """Build the structured write_file permission for a proposal.

        Args:
            proposal: the WorldActionProposal; ``params`` must carry the
                ``old_lines`` / ``new_lines`` hunks.
            permitted_by: the authorization source.

        Returns:
            A ToolPermission carrying the structured patch spec.
        """
        params = dict(getattr(proposal, "params", {}) or {})
        old_lines = list(params.get("old_lines", []) or [])
        new_lines = list(params.get("new_lines", []) or [])
        return ToolPermission(
            tool_name=self.tool_name,
            args=[{"path": self.target, "old_lines": old_lines,
                   "new_lines": new_lines}],
            cwd=self.executor.workspace_root,
            permitted_by=permitted_by,
        )

    def _observed_content(self, observation: WorldObservation) -> Optional[str]:
        """Extract the content string from an observation.

        Args:
            observation: the observation to read.

        Returns:
            The content string, or None when absent/unreadable.
        """
        state = getattr(observation, "state", None)
        if isinstance(state, dict):
            if not state.get("exists", False):
                return None
            content = state.get("content")
            return content if isinstance(content, str) else None
        return None

    def verify_result(self, prediction: Any,
                      observation: WorldObservation) -> VerificationResult:
        """Compare predicted content against the observed content.

        Args:
            prediction: the expected full file content (str), or a mapping
                carrying a ``"content"`` key.
            observation: the later observation of the target file.

        Returns:
            VerificationResult: exact content match -> gap 0.0, else gap 1.0.
        """
        expected = prediction
        if isinstance(prediction, dict):
            expected = prediction.get("content")
        observed = self._observed_content(observation)
        matched = (expected is not None and observed is not None
                   and str(expected) == str(observed))
        return VerificationResult(
            matched=matched,
            reality_gap=0.0 if matched else 1.0,
            predicted=expected,
            observed=observed,
            detail=("observed content matches the prediction"
                    if matched else
                    "observed content does not match the prediction"),
        )


__all__ = [
    "WorldAdapter", "WorldObservation", "ValidationResult", "VerificationResult",
    "AdapterRefused", "FilesystemWriteAdapter", "DEFAULT_OBSERVE_CHARS",
]
