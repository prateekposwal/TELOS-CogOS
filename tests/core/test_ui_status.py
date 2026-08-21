"""Contract tests for ThinkingDisplay — the live pipeline status indicator
(DI/MD, active phase, cycle; freezes cleanly and renders only when enabled).
"""
import io
import sys

from telos.core.ui.status import ThinkingDisplay


def test_phases_are_canonical():
    assert ThinkingDisplay.PHASE_LABELS == [
        "perceive", "streams", "simulate", "evaluate",
        "synthesis", "select", "council", "act", "reflect",
    ]
    assert len(ThinkingDisplay.PHASE_EMOJI) == 9


def test_disabled_display_renders_nothing(capsys):
    d = ThinkingDisplay(enabled=False)
    d.on_cycle_start(1)
    d.on_phase_start("perceive")
    out = capssys_read(capsys)
    assert out == ""


def test_enabled_display_renders_cycle(capsys):
    d = ThinkingDisplay(enabled=True)
    d.on_cycle_start(3)
    d.on_phase_start("council")
    out = capssys_read(capsys)
    assert "Cycle 3" in out
    assert "COUNCIL" in out


def test_freeze_writes_and_flags(capsys):
    d = ThinkingDisplay(enabled=True)
    d.on_cycle_start(1)
    d.freeze()
    assert d._frozen is True
    out = capssys_read(capsys)
    assert "\n\n" in out


def test_phase_emoji_map_covers_labels():
    d = ThinkingDisplay()
    for name in d.PHASE_LABELS:
        assert name in d.PHASE_EMOJI


def capssys_read(capsys):
    """Read captured stdout/stderr and return combined string."""
    captured = capsys.readouterr()
    return captured.out + captured.err