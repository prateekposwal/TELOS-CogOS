"""
ToolRegistry — the canonical source of TELOS's executable tool set.

The registry must be the single declaration of the allowlist; ACTION_ALLOWLIST
is a projection of it, so the executor, audit tools, and docs cannot drift.
"""

import pytest

from telos.core.actions.registry import (
    ToolRegistry, DEFAULT_REGISTRY, ToolSpec, AllowlistEntry, VALID_KINDS,
)
from telos.core.actions.executor import ACTION_ALLOWLIST

EXPECTED_TOOLS = [
    "eslint_check", "git_add", "git_branch", "git_commit", "git_diff",
    "git_log", "git_status", "go_test", "make_target", "npm_build",
    "npm_test", "run_tests", "tsc_check", "write_file",
]


def test_default_registry_has_expected_tools():
    """The canonical registry holds exactly the 14 audited tools."""
    assert DEFAULT_REGISTRY.names() == sorted(EXPECTED_TOOLS)


def test_action_allowlist_is_projection_of_registry():
    """ACTION_ALLOWLIST must expose the SAME specs as the registry."""
    assert sorted(ACTION_ALLOWLIST) == DEFAULT_REGISTRY.names()
    for name, spec in ACTION_ALLOWLIST.items():
        assert spec is DEFAULT_REGISTRY.get(name), \
            "executor allowlist must not fork the registry's specs"


def test_allowlist_entry_is_toolspec_alias():
    """The legacy AllowlistEntry name is the same dataclass (one source)."""
    assert AllowlistEntry is ToolSpec


def test_every_spec_is_well_formed():
    """Each spec carries a list template, a valid kind, description, family."""
    for spec in ACTION_ALLOWLIST.values():
        assert isinstance(spec.template, list) and spec.template
        assert spec.kind in VALID_KINDS
        assert spec.description
        assert spec.family


def test_families_partition_all_tools():
    """Every tool belongs to exactly one family; >=3 families exist."""
    fams = DEFAULT_REGISTRY.families()
    assert len(fams) >= 3
    all_names = [n for names in fams.values() for n in names]
    assert sorted(all_names) == DEFAULT_REGISTRY.names()


def test_registry_rejects_invalid_kind():
    """A malformed spec fails loudly at construction, not silently at runtime."""
    with pytest.raises(ValueError):
        ToolRegistry({"bad": ToolSpec(template=["x"], kind="nope", description="d")})


def test_registry_rejects_empty_description():
    """A spec with no description is rejected at construction."""
    with pytest.raises(ValueError):
        ToolRegistry({"bad": ToolSpec(template=["x"], kind="read_only", description="")})


def test_registry_lookup_helpers():
    """get/contains/len behave as a normal registry."""
    assert DEFAULT_REGISTRY.get("git_status") is not None
    assert DEFAULT_REGISTRY.get("no_such_tool") is None
    assert "git_status" in DEFAULT_REGISTRY
    assert len(DEFAULT_REGISTRY) == len(EXPECTED_TOOLS)


def test_no_template_contains_shell_operators():
    """Defense in depth: no spec's argv contains shell operators."""
    for spec in ACTION_ALLOWLIST.values():
        joined = " ".join(spec.template)
        for ch in (";", "&&", "|", "$(", "`"):
            assert ch not in joined, f"shell operator {ch!r} in {spec.template}"
