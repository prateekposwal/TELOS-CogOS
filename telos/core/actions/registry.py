"""
ToolRegistry — the single canonical source of TELOS's real-tool allowlist.

PATTERN (one canonical source): every executable tool is declared EXACTLY ONCE
here as a ToolSpec. The ActionExecutor builds its allowlist from this registry,
so the set of tools TELOS may run cannot drift between the documented list, the
executor, and the audit tooling — the schema-drift failure mode, killed at the
source (Λ6.7: one canonical registry, no consumer invents its own).

A spec is DATA, not authority. The executor still performs the four hard gates
(operator permission, registry membership + template validation, firewall
audit, bounded capture). The registry only answers: what is a tool, which
family does it belong to, and which capability does it require?

Families give the audit a coarse, honest taxonomy (git_read, test_run,
toolchain, git_write, structured_write) so coverage can be measured rather
than asserted. ``capability`` binds per-tool capability authorization; every
spec carries a non-None ``rate_limit_per_min`` that ActionExecutor ENFORCES at
the one execution boundary (per-tool sliding window + per-session budget). No
spec is left declared-but-None: an unenforced limit is not a limit.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional

# Valid tool kinds. read_only never mutates; narrow_write is an operator-scoped
# mutation (git add/commit); structured_write applies a validated patch object
# with no subprocess at all; network_read/write leave via NetworkSandbox.
VALID_KINDS = ("read_only", "narrow_write", "structured_write",
               "network_read", "network_write")


@dataclass
class ToolSpec:
    """One allowlisted tool: its argv template, classification, and family.

    Attributes:
        template: argv list; placeholders {n}, {path}, {message}, {target},
            {patch} are validated before substitution (int range / path
            containment / safe charset).
        kind: one of read_only / narrow_write / structured_write.
        description: human-readable statement of what this tool may do.
        family: coarse audit taxonomy (git_read, test_run, toolchain,
            git_write, structured_write).
        capability: optional capability-authorization profile key. Declared
            now; enforced per-tool in Phase 1 (currently None).
        rate_limit_per_min: per-tool invocation ceiling (invocations in the
            trailing 60s), enforced by ActionExecutor's ToolRateLimiter. Every
            canonical spec sets a real value (never None).
    """

    template: List[str]
    kind: str
    description: str
    family: str = "toolchain"
    capability: Optional[str] = None
    rate_limit_per_min: Optional[int] = None


# Backwards-compatible name: the executor and its consumers long referred to
# this record as an AllowlistEntry. It is the SAME dataclass — one source.
AllowlistEntry = ToolSpec


def _default_specs() -> Dict[str, ToolSpec]:
    """Build the canonical default tool specs.

    Returns:
        Mapping of tool name -> ToolSpec (the 14 audited tools).
    """
    return {
        "git_status": ToolSpec(
            template=["git", "status", "--porcelain"],
            kind="read_only", family="git_read",
            rate_limit_per_min=60,
            description="Report the repository's working-tree/index changes (porcelain).",
        ),
        "git_branch": ToolSpec(
            template=["git", "branch", "--show-current"],
            kind="read_only", family="git_read",
            rate_limit_per_min=60,
            description="Report the currently checked-out branch name.",
        ),
        "git_log": ToolSpec(
            template=["git", "log", "-n", "{n}", "--oneline"],
            kind="read_only", family="git_read",
            rate_limit_per_min=60,
            description="List the N most recent commits, one line each (N in 1..30).",
        ),
        "git_diff": ToolSpec(
            template=["git", "diff"],
            kind="read_only", family="git_read",
            rate_limit_per_min=60,
            description="Show the unified diff of unstaged changes (read-only).",
        ),
        "run_tests": ToolSpec(
            template=[sys.executable, "-m", "pytest", "{path}", "-q", "--tb=short"],
            kind="read_only", family="test_run",
            rate_limit_per_min=6,
            description="Run pytest on a path INSIDE the operator's workspace root.",
        ),
        "write_file": ToolSpec(
            template=["write_file", "{patch}"],
            kind="structured_write", family="structured_write",
            rate_limit_per_min=6,
            description=(
                "Apply a SUBMITTED structured minimal patch (path + old_lines + "
                "new_lines) to an EXISTING TRACKED file inside the workspace. "
                "Never accepts freeform shell; a blocked write writes nothing."
            ),
        ),
        "git_add": ToolSpec(
            template=["git", "add", "{path}"],
            kind="narrow_write", family="git_write",
            rate_limit_per_min=12,
            description="Stage a path INSIDE the workspace (prerequisite of git_commit).",
        ),
        "git_commit": ToolSpec(
            template=["git", "commit", "-m", "{message}"],
            kind="narrow_write", family="git_write",
            rate_limit_per_min=6,
            description="Create a commit whose message the council approved (<=200 chars).",
        ),
        "tsc_check": ToolSpec(
            template=["tsc", "--noEmit", "{path}"],
            kind="read_only", family="toolchain",
            rate_limit_per_min=20,
            description="Type-check a path (tsconfig/project) INSIDE the workspace with --noEmit.",
        ),
        "eslint_check": ToolSpec(
            template=["eslint", "{path}"],
            kind="read_only", family="toolchain",
            rate_limit_per_min=20,
            description="Lint a path INSIDE the workspace with eslint.",
        ),
        "npm_test": ToolSpec(
            template=["npm", "--prefix", "{path}", "test"],
            kind="read_only", family="toolchain",
            rate_limit_per_min=6,
            description="Run `npm test` in a package INSIDE the workspace (--prefix confined).",
        ),
        "npm_build": ToolSpec(
            template=["npm", "--prefix", "{path}", "run", "build"],
            kind="read_only", family="toolchain",
            rate_limit_per_min=6,
            description="Run `npm run build` in a package INSIDE the workspace (--prefix confined).",
        ),
        "make_target": ToolSpec(
            template=["make", "{target}"],
            kind="read_only", family="toolchain",
            rate_limit_per_min=20,
            description="Run a make target whose Makefile lives INSIDE the workspace cwd.",
        ),
        "go_test": ToolSpec(
            template=["go", "test", "./..."],
            kind="read_only", family="toolchain",
            rate_limit_per_min=6,
            description="Run `go test ./...` in a subdirectory of the workspace (cwd governed).",
        ),
        # ── Governed network family (Phase 1): every request leaves through
        # NetworkSandbox (host/port/route allowlist + bounded payloads). These
        # require the network capability profiles, not just observability. ──
        "http_post": ToolSpec(
            template=["http_post", "{url}", "{body}"],
            kind="network_read", family="network_read",
            capability="network_read",
            rate_limit_per_min=20,
            description=(
                "POST JSON to an allowlisted HTTPS endpoint through the governed "
                "NetworkSandbox; response is bounded and audited."
            ),
        ),
        "http_get": ToolSpec(
            template=["http_get", "{url}"],
            kind="network_read", family="network_read",
            capability="network_read",
            rate_limit_per_min=60,
            description=(
                "GET an allowlisted HTTPS endpoint through the governed "
                "NetworkSandbox; response is bounded and audited."
            ),
        ),
    }


class ToolRegistry:
    """An ordered, queryable collection of ToolSpecs.

    The registry is the ONLY place the executable tool set is defined. It is
    intentionally small: membership, family taxonomy, and capability bindings —
    never execution. Execution authority stays in ActionExecutor's four gates.
    """

    def __init__(self, specs: Optional[Dict[str, ToolSpec]] = None):
        """Construct a registry from an explicit spec mapping.

        Args:
            specs: tool name -> ToolSpec. Defaults to the canonical set.
        """
        self._specs: Dict[str, ToolSpec] = dict(
            _default_specs() if specs is None else specs
        )
        self._validate()

    def _validate(self) -> None:
        """Reject a malformed registry at construction (fail loud, not late).

        Raises:
            ValueError: if any spec has an invalid kind or empty description.
        """
        for name, spec in self._specs.items():
            if spec.kind not in VALID_KINDS:
                raise ValueError(
                    f"tool {name!r} has invalid kind {spec.kind!r} "
                    f"(expected one of {VALID_KINDS})"
                )
            if not spec.description:
                raise ValueError(f"tool {name!r} has an empty description")
            # An unenforced/undeclared limit is not a limit: every tool MUST
            # carry a real positive per-minute ceiling (fail loud at
            # construction, not silently at execution time).
            if not isinstance(spec.rate_limit_per_min, int) \
                    or spec.rate_limit_per_min <= 0:
                raise ValueError(
                    f"tool {name!r} must declare a positive int "
                    f"rate_limit_per_min (got {spec.rate_limit_per_min!r})"
                )

    @classmethod
    def default(cls) -> "ToolRegistry":
        """Return the canonical registry (the 14 audited tools).

        Returns:
            A fresh ToolRegistry over the default specs.
        """
        return cls()

    def get(self, name: str) -> Optional[ToolSpec]:
        """Return the spec for a tool name, or None.

        Args:
            name: the tool name to look up.

        Returns:
            The ToolSpec, or None when the name is not on the allowlist.
        """
        return self._specs.get(name)

    def add(self, name: str, spec: ToolSpec) -> None:
        """Register (or replace) one tool spec.

        Args:
            name: the tool name.
            spec: the ToolSpec to register.
        """
        self._specs[name] = spec
        self._validate()

    def names(self) -> List[str]:
        """Return the sorted tool names.

        Returns:
            Sorted list of allowlisted tool names.
        """
        return sorted(self._specs)

    def families(self) -> Dict[str, List[str]]:
        """Group tool names by family.

        Returns:
            Mapping family -> sorted tool names in that family.
        """
        out: Dict[str, List[str]] = {}
        for name, spec in self._specs.items():
            out.setdefault(spec.family, []).append(name)
        return {fam: sorted(names) for fam, names in sorted(out.items())}

    def as_allowlist(self) -> Dict[str, ToolSpec]:
        """Return a shallow copy of the spec mapping (executor-compatible).

        Returns:
            Dict of tool name -> ToolSpec.
        """
        return dict(self._specs)

    def __contains__(self, name: object) -> bool:
        return name in self._specs

    def __iter__(self) -> Iterator[str]:
        return iter(self._specs)

    def __len__(self) -> int:
        return len(self._specs)


# The one shared default instance. ActionExecutor reads THIS to build its
# allowlist; the tool-channel scanner reads it to know which executable paths
# are governed.
DEFAULT_REGISTRY = ToolRegistry.default()


# Capability profiles: which CapabilityAuthorization gates a tool family
# requires to be PASS/LIMITED before the tool may run. Read by the executor's
# per-tool gate (Phase 1). A profile names the gates that MUST be authorized;
# a FAIL on any of them vetoes that tool exactly as a council veto blocks an
# action (conjunctive, non-tradeable — mirroring CapabilityAuthorization).
#
# read-only observation tools require only observability; mutation/write tools
# additionally require action_validity (the action is in the action space),
# authority (we are entitled to mutate), and model_fidelity (the world model
# backing the mutation is validated against reality — the measured authority
# from the post-action Reality Gap). Network-capable families additionally
# require causal_confidence + recovery.
CAPABILITY_PROFILES: Dict[str, List[str]] = {
    "read_only": ["observability"],
    "narrow_write": ["observability", "action_validity", "authority",
                     "model_fidelity"],
    "structured_write": ["observability", "action_validity", "authority",
                         "model_fidelity"],
    "network_read": ["observability", "causal_confidence"],
    "network_write": ["observability", "action_validity", "authority",
                      "model_fidelity", "causal_confidence", "recovery"],
}


def capability_profile_for(spec: "ToolSpec") -> List[str]:
    """Return the capability gates a tool's kind requires.

    Args:
        spec: the tool spec (its declared ``capability`` wins when set,
            otherwise its kind determines the profile).

    Returns:
        List of gate names that must be authorized for this tool.
    """
    if spec.capability and spec.capability in CAPABILITY_PROFILES:
        return list(CAPABILITY_PROFILES[spec.capability])
    return list(CAPABILITY_PROFILES.get(spec.kind, ["observability"]))


__all__ = [
    "ToolSpec", "AllowlistEntry", "ToolRegistry", "DEFAULT_REGISTRY",
    "VALID_KINDS", "CAPABILITY_PROFILES", "capability_profile_for",
]
