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

## The double-application A/B (done — decision: keep control)

Toggle: `TELOS_POLICY_MOOD_SINGLE_SOURCE=1` disables the duplicate
KnowledgeManager application (InfrastructureManager's ×0.3 remains the only
one). Same workload, same seed:

| Metric | control (double) | single-source |
|---|---:|---:|
| action emission | 0.893 | 0.893 |
| no-op rate | 0.107 | 0.107 |
| episodes | 16 | 16 |
| mean DI | 1.000 | 1.000 |
| low_integrity blocks | 0 | 0 |
| risk_tolerance mean | **0.197** | 0.101 |
| firewall DI threshold mean | **0.803** | 0.899 |

**Throughput and health are identical; single-sourcing only makes the firewall
stricter** (removing the full-strength application strips a *loosening* bias
that mood:curious contributed). Per the acceptance rule ("no worse on
throughput/evidence/safety"), **control is the better default** — it keeps the
system more permissive at no cost. The duplicate is a design smell (one signal,
two applications) but not a defect in effect; the env toggle is retained for
future worlds where the bias may matter. No default change.

## Symmetric uncertainty→risk (done — enabled)

`adjust_risk_by_uncertainty` was tighten-only. A bounded loosen-under-
certainty branch was added (`+0.5·risk·(CERTAINTY_MAX − avg_uncertainty)` when
`avg_uncertainty ≤ CERTAINTY_MAX = 0.2`; identical to the old path at/above the
threshold, so continuity holds). A/B (env `TELOS_RISK_SYMMETRIC_UNCERTAINTY`):

| Metric | tighten-only | symmetric |
|---|---:|---:|
| action / no-op / episodes / DI | 0.893 / 0.107 / 16 / 1.0 | **identical** |
| risk_tolerance mean | 0.197 | **0.209** |
| firewall DI threshold mean | 0.803 | **0.791** |

Identical health/safety, one-sided bias corrected → **enabled by default**
(opt-out `TELOS_RISK_SYMMETRIC_UNCERTAINTY=0`).

## Gates

- `make check` — release/CI gate (full duration, ~3 min): pytest + self-audit +
  falsifier + theorems + cognitive health.
- `make check-fast` — per-commit gate (reduced sim duration; episode threshold
  scales with cycle count).
- `.github/workflows/gates.yml` runs `make check` on PRs.

## LEFT

- The mood double-application stays by decision (A/B above), documented.
- Nothing load-bearing remains in the policy/threshold area.
