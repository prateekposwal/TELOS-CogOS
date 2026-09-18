"""
CLI integration tests for load-bearing developer workflows.

These tools are invoked by hand, not by the pipeline — but two of them ARE the
project's safety gates (the axiom falsifier and the coverage SSoT), so their
end-to-end CLI behavior is worth protecting.
"""
from telos.tools.falsify_axioms import main as falsify_main
from telos.tools.coverage_priority import main as coverage_main


def test_falsify_axioms_cli_passes(capsys):
    assert falsify_main(["--ci"]) == 0
    out = capsys.readouterr().out
    assert "FALSIFIABILITY GATE: PASS" in out
    assert "42/42" in out


def test_coverage_priority_cli_runs(capsys):
    assert coverage_main(["--top", "1"]) == 0
    out = capsys.readouterr().out
    assert "referenced-by-test" in out
