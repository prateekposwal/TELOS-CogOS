"""
Tool-channel scanner — every production subprocess/http call site is classified.

TELOS may touch the real world only through the ActionExecutor. This scanner
must find zero UNKNOWN (undocumented, ungoverned) channels in production code,
while reporting the documented Phase-1 bypasses explicitly.
"""

from telos.tools.tool_channel_scan import (
    scan, classify, iter_call_sites, KNOWN_BYPASSES, GOVERNED,
)


def test_scan_finds_no_unknown_channels():
    """No production call site outside the governed channel / known bypasses."""
    result = scan()
    assert result["counts"]["unknown_sites"] == 0, result["unknown"]


def test_executor_channel_is_governed():
    """The ActionExecutor itself is the one governed site."""
    result = scan()
    assert result["counts"]["governed_sites"] >= 1
    assert any(g["path"] in GOVERNED for g in result["governed"])


def test_model_provider_is_a_documented_bypass():
    """The network chat providers are reported, not hidden."""
    result = scan()
    paths = [entry["path"] for entry in result["known_bypasses"]]
    assert "telos/core/contracts/model_provider.py" in paths
    assert all(entry["reason"] for entry in result["known_bypasses"])


def test_classify_statuses():
    """Classify maps governed / known_bypass / unknown correctly."""
    assert classify("telos/core/actions/executor.py")["status"] == "governed"
    assert classify("telos/core/contracts/model_provider.py")["status"] == "known_bypass"
    assert classify("telos/core/somewhere/new_channel.py")["status"] == "unknown"


def test_iter_call_sites_detects_subprocess(tmp_path):
    """An ast-detected subprocess.run is a subprocess call site."""
    f = tmp_path / "mod.py"
    f.write_text("import subprocess\nsubprocess.run(['ls'])\n")
    sites = iter_call_sites(str(f))
    assert any(s["kind"] == "subprocess" for s in sites)


def test_iter_call_sites_detects_network(tmp_path):
    """An ast-detected http.client construction is a network call site."""
    f = tmp_path / "net.py"
    f.write_text("import http.client\nc = http.client.HTTPSConnection('x')\n")
    sites = iter_call_sites(str(f))
    assert any(s["kind"] == "network" for s in sites)


def test_iter_call_sites_ignores_comments(tmp_path):
    """A comment mentioning subprocess.run is not a real call site."""
    f = tmp_path / "doc.py"
    f.write_text("# subprocess.run explains the pattern\nx = 1\n")
    assert iter_call_sites(str(f)) == []


def test_known_bypasses_are_documented():
    """Every documented bypass carries a non-empty migration reason."""
    assert "telos/core/contracts/model_provider.py" in KNOWN_BYPASSES
    for reason in KNOWN_BYPASSES.values():
        assert reason.strip()
