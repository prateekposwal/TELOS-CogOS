"""
Real-world action path safety — determinism isolation + default-OFF.

PATTERN UNDER TEST (a determinism gate is a hard boundary): a LIVE executor is
non-deterministic by construction, so a determinism-gated pipeline refuses one
at construction rather than silently running it. Default config stays OFF.
"""

import tempfile

import pytest

from telos.core.actions.executor import build_tool_executor
from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.actions.certification import DEFAULT_CERTIFICATION_PATH


def test_determinism_gate_rejects_executor():
    """Determinism gate + workspace + permission is a hard config error."""
    ws = tempfile.mkdtemp(prefix="telos_detgate_")
    with pytest.raises(ValueError):
        TelosV14Pipeline(PipelineConfig(
            tool_workspace=ws, operator_tool_permission=True,
            determinism_gate=True))


def test_determinism_gate_rejects_preset_executor():
    """Determinism gate + a pre-set action_executor is refused."""
    ws = tempfile.mkdtemp(prefix="telos_detgate2_")
    ex = build_tool_executor(ws)
    with pytest.raises(ValueError):
        TelosV14Pipeline(PipelineConfig(
            action_executor=ex, determinism_gate=True))


def test_determinism_gate_without_executor_is_fine():
    """A determinism-gated pipeline with no executor constructs cleanly."""
    p = TelosV14Pipeline(PipelineConfig(determinism_gate=True))
    assert p.config.action_executor is None


def test_default_config_is_off_and_not_gated():
    """Default config: no executor, no workspace, gate off (byte-identical)."""
    p = TelosV14Pipeline(PipelineConfig())
    assert p.config.action_executor is None
    assert p.config.tool_workspace is None
    assert p.config.operator_tool_permission is False
    assert p.config.determinism_gate is False


def test_certification_path_is_the_audit_record():
    """The canonical certification record lives under the audit tree."""
    assert DEFAULT_CERTIFICATION_PATH.endswith(
        "telos/audit/capability_certification.json")
