"""
External Axiom Falsifier CLI — attack the constitution and report coverage.

Runs the adversarial sabotage suite against the real AxiomProver. Exit 1 in
--ci mode if the healthy baseline fails or any axiom is unfalsifiable, so the
gate can never pass by silence.

Usage:
    PYTHONPATH=. python3 telos/tools/falsify_axioms.py
    PYTHONPATH=. python3 telos/tools/falsify_axioms.py --ci
"""
import sys

from telos.core.verifier.axiom_falsifier import AxiomFalsifier


def main(argv=None) -> int:
    """Run the falsifier and print a coverage report.

    Args:
        argv: optional argv list (defaults to sys.argv).

    Returns:
        Process exit code (0 = all axioms falsifiable, 1 = gap).
    """
    argv = sys.argv[1:] if argv is None else argv
    ci = "--ci" in argv

    report = AxiomFalsifier().run()
    print("TELOS Axiom Falsifier — external adversarial coverage")
    print("=" * 60)
    print(f"  healthy baseline passes : {report['healthy_passed']}")
    if report["healthy_failed"]:
        print(f"  healthy baseline FAILED : {report['healthy_failed']}")
    print(f"  falsifiable              : {len(report['falsifiable'])}/42")
    print(f"  unfalsifiable            : {report['unfalsifiable'] or 'none'}")
    print("=" * 60)

    if not report["healthy_passed"] or report["unfalsifiable"]:
        print("FALSIFIABILITY GATE: FAIL")
        return 1 if ci else 0
    print("FALSIFIABILITY GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
