# telos-verify — an external auditor for any agent's decision log

> **Purpose.** TELOS's trust claim should not require trusting TELOS. This is a
> portable, offline, producer-agnostic auditor: point it at any JSON decision
> log and it returns a three-axis integrity scorecard with the evidence behind
> every number.

## What it measures

| Axis | Question | Scored 0 when |
|------|----------|---------------|
| **Epistemic integrity** | Is each decision's integrity *reported* in [0,1]? | a record omits integrity or reports it outside [0,1] |
| **Governance coverage** | Did the decision path record a validation gate at all? | no `council_validated`/`validated`/`governance_blocked` field |
| **Computational integrity** | Where budgets are reported, does consumption stay within budget? | `consumed > 1.1 × total` |

The composite is computed **only over the axes that are measurable**. Absent
axes are reported as `None` and explained in `notes` — never imputed.

## Usage

```bash
PYTHONPATH=. python3 telos/tools/verify_decision_log.py --json log.json
cat log.json | PYTHONPATH=. python3 telos/tools/verify_decision_log.py --ci --threshold 0.5
```

On a real 6-cycle TELOS run:

```
records audited      : 6
epistemic integrity  : 1.000
computational integ. : 1.000
governance coverage  : 1.000
composite            : 1.000  (grade A)
```

## Why this matters competitively

- **vs LLM agent frameworks:** they emit logs, but nothing neutral scores them.
  telos-verify is that neutral scorer.
- **vs formal methods (TLA+, Coq):** those prove designs, not running logs.
  telos-verify audits *what an agent actually did*.
- **vs "trust us" alignment claims:** an external party can now run the check
  themselves — which is the precondition for the D5 external-reproduction gate.

## Accepted input shapes

A JSON **list** of records, or a dict with a `decisions` / `traces` /
`records` / `log` list. Each record may carry:

- `decision_integrity` (or `integrity`)
- `council_validated` / `validated` / `governance_blocked`
- `budget_consumed_ms` / `consumed_ms` and `budget_total_ms` / `budget_ms`

Unknown fields are ignored; the scorer never invents data.

## Implementation

- Core (pure, importable): `telos/core/verifier/decision_log_audit.py`
- CLI: `telos/tools/verify_decision_log.py`
- Tests: `tests/core/test_verify_decision_log.py`
