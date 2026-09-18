# Mission-policy audit — the firewall DI threshold and its up-driver

`MissionPolicy.firewall_di_threshold = 1 − risk_tolerance`. The firewall's
strictness is therefore entirely a function of `risk_tolerance`. Instrument:
`telos/core/decision/policy_trace.py` (per-cycle posture + recent mutations,
non-behavioral, on every trace). Audit: `telos/tools/policy_audit.py`.

## Who raises the threshold

150 cycles, real GridWorld workload, **after** the circular-evidence fix
(`research/COUNCIL_GATE.md`):

```
risk_tolerance        : min 0.083  mean 0.197  max 0.307   (at floor 0.05: 0)
firewall_di_threshold : min 0.693  mean 0.803  max 0.917
policy_changes=986  unlabeled=0
by caller:
   200x risk_tolerance::knowledge_manager
   150x risk_tolerance::system_self
   135x risk_tolerance::adjust_risk_by_uncertainty
```

So the down-drivers (which push the threshold UP) are:

1. **Mood → risk** (`SystemSelf.get_risk_adjustment`), applied from **two**
   sites: `InfrastructureManager.observe` (`×0.3`, caller `system_self`) and
   `KnowledgeManager.observe` (**full strength**, caller `knowledge_manager`).
2. **Stream uncertainty** (`adjust_risk_by_uncertainty`) — which only ever
   *tightens* (`target = risk·(1 − 0.5·uncertainty)`); there is no symmetric
   loosen-on-certainty path.

The loose-up path is weak: identity markers (`+0.02`) and the exploration-budget
increase on stable periods. Net structural bias is **tighten**.

## Findings

- **No railing.** After the circular-evidence fix, `risk_tolerance` never hits
  its 0.05 floor (min 0.083); the threshold peaked at 0.917, not 0.95. The old
  rail was caused by the circular `low_integrity` failure pressure, now gone.
- **Harmless while DI = 1.0.** A high threshold only blocks if DI drops below
  it; with the evidence loop broken, DI is 1.0, so the high threshold is inert.
- **Telemetry gap closed.** 335 policy mutations carried no caller/reason; all
  unlabeled call sites now record `caller`/`reason` (audit: `unlabeled=0`).
- **Double-scaled mood adjustment (flagged, NOT changed).** The same mood
  signal is applied at full strength in `KnowledgeManager` and at ×0.3 in
  `InfrastructureManager`. A blind dedup was A/B-tested and made the threshold
  *worse* (mean 0.803 → 0.899) — a trajectory effect, not a clean win. Per the
  instrument-first rule it is **left unchanged**, documented for a proper
  experiment, with labels added so the audit can see it.

## LEFT

- Decide (by experiment, not edit) whether the mood adjustment should be
  single-sourced and scaled once, and whether `adjust_risk_by_uncertainty`
  needs a symmetric loosen path. Now low-risk: DI is 1.0 and the threshold is
  inert, so this is hygiene, not a throughput blocker.
