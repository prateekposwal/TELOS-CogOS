"""
Tool-channel scanner — every production subprocess/http call site is classified.

TELOS may touch the real world only through a governed channel: subprocesses via
the ActionExecutor, network via the NetworkSandbox. This scanner must find zero
UNKNOWN (undocumented, ungoverned) channels in production code, while reporting
any explicit, reviewed exemption explicitly.
"""

from telos.tools.tool_channel_scan import (
    scan, classify, iter_call_sites, exemptions_reviewed, EXEMPTIONS, GOVERNED,
)


def test_scan_finds_no_unknown_channels():
    """No production call site outside a governed channel / reviewed exemption."""
    result = scan()
    assert result["counts"]["unknown_sites"] == 0, result["unknown"]


def test_no_known_bypasses_remain():
    """The Phase-1 debt is zero: known bypasses are governed or reviewed."""
    result = scan()
    assert result["counts"]["known_bypass_sites"] == 0


def test_executor_channel_is_governed():
    """The governed channels are detected as call sites."""
    result = scan()
    assert result["counts"]["governed_sites"] >= 1
    assert any(g["path"] in GOVERNED for g in result["governed"])


def test_model_provider_is_governed_no_longer_a_bypass():
    """The chat providers route through NetworkSandbox — no raw http.client."""
    result = scan()
    assert "telos/core/contracts/model_provider.py" not in EXEMPTIONS
    assert not any(g["path"] == "telos/core/contracts/model_provider.py"
                   for g in result["unknown"])
    # It has no ungoverned call sites at all now.
    assert not any(e["path"] == "telos/core/contracts/model_provider.py"
                   for e in result["exemptions"])


def test_human_gateway_is_governed_no_longer_a_bypass():
    """The webhook review routes through NetworkSandbox — no raw http.client."""
    result = scan()
    assert "telos/core/governance/human_gateway.py" not in EXEMPTIONS
    assert not any(e["path"] == "telos/core/governance/human_gateway.py"
                   for e in result["exemptions"])


def test_classify_statuses():
    """Classify maps governed / exempt / unknown correctly."""
    assert classify("telos/core/actions/executor.py")["status"] == "governed"
    assert classify("telos/core/actions/sandbox.py")["status"] == "governed"
    assert classify("telos/adapters/dev_validation.py")["status"] == "exempt"
    assert classify("telos/core/somewhere/new_channel.py")["status"] == "unknown"


def test_exemptions_are_explicit_and_reviewed():
    """Every exemption names a reason + governing plan and is reviewed."""
    for path, meta in EXEMPTIONS.items():
        assert meta["reason"].strip(), path
        assert meta["governed_by"].strip(), path
        assert meta["reviewed"] == "true", path
    assert exemptions_reviewed(scan()) is True


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
