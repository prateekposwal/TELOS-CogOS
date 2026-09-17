"""
telos-verify — score any agent's decision log for epistemic/computational integrity.

Portable, offline, and producer-agnostic: reads a JSON decision log (list of
records or a dict carrying one) and prints a three-axis scorecard with the
evidence behind every number. No TELOS internals, no trust in the producer.

Usage:
    PYTHONPATH=. python3 telos/tools/verify_decision_log.py --json log.json
    cat log.json | PYTHONPATH=. python3 telos/tools/verify_decision_log.py --ci
"""
import argparse
import json
import sys

from telos.core.verifier.decision_log_audit import score_log


def _fmt(value) -> str:
    """Format a score for the table.

    Args:
        value: float or None.

    Returns:
        A display string.
    """
    return "n/a" if value is None else f"{value:.3f}"


def main(argv=None) -> int:
    """Run the auditor and print the scorecard.

    Args:
        argv: optional argv list (defaults to sys.argv).

    Returns:
        Exit code (0 = pass or report-only, 1 = below threshold in --ci).
    """
    parser = argparse.ArgumentParser(description="telos-verify decision-log audit")
    parser.add_argument("--json", help="path to the decision log (default: stdin)")
    parser.add_argument("--ci", action="store_true",
                        help="exit 1 if composite < --threshold")
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.json:
        with open(args.json) as fh:
            payload = json.load(fh)
    else:
        payload = json.load(sys.stdin)

    report = score_log(payload)

    print("\n            telos-verify — decision-log integrity scorecard")
    print("=" * 66)
    print(f"  records audited      : {report['n']}")
    print(f"  epistemic integrity  : {_fmt(report['epistemic'])}")
    print(f"  computational integ. : {_fmt(report['computational'])}")
    print(f"  governance coverage  : {_fmt(report['governance'])}")
    print(f"  composite            : {_fmt(report['composite'])}  "
          f"(grade {report['grade']})")
    for note in report["notes"]:
        print(f"  note                 : {note}")
    print("=" * 66)

    if args.ci:
        if report["composite"] is None:
            print("VERIFY: FAIL (nothing measurable)")
            return 1
        if report["composite"] < args.threshold:
            print(f"VERIFY: FAIL (composite {report['composite']:.3f} < {args.threshold})")
            return 1
        print("VERIFY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
