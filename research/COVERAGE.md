# Coverage — breakdown, classification, and policy

Real line+branch coverage (coverage.py), grouped by package. Measured by
`telos/tools/branch_coverage.py`. Whole `telos/` is 74.5%; the number is
dragged by hand-run CLI tools, not by the reasoning runtime.

| Group | Branch coverage | Points |
|---|---:|---:|
| `telos/core` (reasoning runtime) | **88.7%** | 22,775 |
| `telos/world` | 91.6% | 321 |
| `telos/audit` | 86.3% | 211 |
| `telos/dashboard` | 84.5% | 742 |
| `telos/adapters` | 72.2% | 1,806 |
| `telos/benchmarks` | 70.1% | 1,979 |
| `telos/examples` | 62.3% | 302 |
| `telos/representations` | 57.6% | 118 |
| `telos/serve_dashboard.py` | 37.0% | 584 |
| `telos/tools` (CLI) | 4.5% | 3,116 |
| `telos/ideation` | 0.0% | 534 |
| `telos/server_bridge.py` | 0.0% | 394 |
| `telos/cli.py` | 0.0% | 117 |

---

## Classification of uncovered points (A–E)

| Class | What | Where | Action |
|---|---|---|---|
| **A — production-critical** | reasoning/runtime paths whose failure changes decisions | `core/phases/*`, `core/governance/*`, `core/decision/*`, `core/verifier/*`, `core/council/*`, `runtime.py` | **Test** — maintain the high bar (≥88%). The metric+policy here is the real guardrail. |
| **B — production utility** | supporting code the runtime reads | `core/**` non-A, `world`, `audit`, `representations`, `adapters` (domain glue) | **Test** when behavior is load-bearing; otherwise leave with the core gate. |
| **C — CLI / manual tooling** | invoked by hand, not by the pipeline | `tools/*` (gap_scanner, self_audit, endurance, perf_profiler…), `cli.py` | **CLI integration tests** where a real user workflow matters (falsify, coverage, verify, selection audit); do not manufacture tests for one-off/experimental runners. |
| **D — defensive / unreachable** | exception fallbacks, `TYPE_CHECKING`, dead guards | scattered `except` arms, mock-leak guards | **Document** — do not manufacture tests just to hit them. |
| **E — generated / integration glue** | external or sibling-service surfaces | `server_bridge.py` (intentional exemption — MD-App sibling), dashboard vendor JS, `examples/*` domains | **Exclude/document** — never chase their percentage. |

## Policy

1. **Gate the runtime, not the toolbelt.** `make coverage` reports with
   `--scope core`; the meaningful denominator is `telos/core`.
2. **No percentage theater.** A test exists to protect a behavior, not a line.
   Class-D/E points are documented here instead of tested.
3. **CLI tests only for real workflows.** `tests/core/test_tools_cli.py` covers
   `falsify_axioms` (the constitution gate) and `coverage_priority` (the
   coverage SSoT) because those are load-bearing developer workflows.
4. **Trend, don't target.** `telos/audit/branch_coverage.json` is the baseline;
   the goal is "no regression + raise A-class", not 100%.
