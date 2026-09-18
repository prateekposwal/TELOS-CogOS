# Council/firewall audit — the circular-evidence loop (found and fixed)

After the ACT-gate audit narrowed the remaining suppression to firewall
governance (`low_integrity` + `action_loop`), this instrument asked: **which
validator dissents, and is the block warranted or a threshold mis-tune?**

Instrument: `telos/core/decision/council_gate_trace.py` (per-cycle dissenters +
DI/threshold + firewall block, non-behavioral, on every trace). Audit:
`telos/tools/council_gate_audit.py`.

## The finding (before the fix)

150 cycles, real GridWorld workload:

```
firewall blocks      : {'low_integrity': 40, 'action_loop': 27}
dissent by validator : {'EvidenceProvenanceValidator': 40}   # 100% of low_integrity
low_integrity source : {'EvidenceProvenanceValidator': 40}
applied DI threshold : {0.95: 35, ...}                       # railed at the 0.95 max
DI                   : mean 0.813, min 0.300                 # floored by one dissent
evidence integrity   : mean 1.000                            # no real evidence problem
top dissent reasons  : "intent type 'blended_inquiry' has N total no-action
                        outcomes — pattern of non-execution"
```

Root cause: **circular evidence.** In `runtime._record_council_outcome`, a cycle
was counted as a "no-action outcome" for its intent type whenever
`selected_action is None`. But a council/firewall-blocked cycle ALSO yields
`selected_action is None` — so the council's own veto was recorded as evidence
about the intent type. `EvidenceProvenanceValidator` then dissented on the
governance-caused no-op → DI floored to `DissentFloor` 0.3 → the firewall
`low_integrity` block (threshold railed to 0.95) recurred **forever**. A
self-reinforcing loop — and a direct violation of TELOS's own canonical rule:

> **governance suppression is not evidence.**

(The rule was already applied to the failure-ledger and KnowledgeGraph paths;
the council's no-action ledger was missed.)

## The fix (canonical rule, one source)

`_record_council_outcome` now excludes governance-suppressed cycles
(`firewall_blocked or council_blocked`) from the no-action evidence ledger.
Only a **genuinely unblocked** no-action counts. Regression:
`tests/core/test_council_evidence_rule.py`.

## After the fix (same workload)

| Metric | Before | After |
|---|---:|---:|
| `low_integrity` blocks | 40 | **0** |
| `EvidenceProvenanceValidator` dissent | 40 | **0** |
| mean DI | 0.813 | **1.000** |
| firewall blocks | 67 | **16** (`action_loop` only) |
| action emitted | 55.3% | **89.3%** |
| no-op rate | 44.7% | **10.7%** |
| episodes completed | 10 | **16** |

So the suppression was **not warranted** — it was circular evidence plus a
threshold railed at its 0.95 ceiling. Breaking the loop collapsed the noise DI
floors and returned action emission to ~90%.

## Remaining (LEFT)

- `action_loop` (16/150) is the firewall's genuine same-action loop detector —
  expected, and the Λ3.1 recovery owns it.
- The **dynamic DI threshold** (`MissionPolicy.firewall_di_threshold`, synced
  into the firewall each cycle) still rails toward 0.95 under failure pressure.
  Now harmless (DI stays 1.0 once the loop is broken) but worth a separate audit
  of the threshold's up-driver — instrument-first, not yet changed.
- Inquiry still dominates *selection* (~97%) but now **executes** (the blended
  intent carries a goal-directed action): moves 134, episodes 16. Selection
  priority is no longer a throughput constraint on this workload.
