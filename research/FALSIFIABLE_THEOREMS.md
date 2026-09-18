# Falsifiable Theorems — TELOS claims restated as measured invariants

> **Why this document exists.** TELOS's original "theorems" were constructive
> existence proofs: *"a validator exists, therefore the axiom holds."* An
> existence proof of an implementation detail is not a prediction — it cannot
> be wrong, so it cannot be science. This document restates the load-bearing
> claims as **measurements with a declared null**: a metric, a threshold, and
> the behaviour that would falsify the claim. Every row is executed by
> `telos/tools/theorem_audit.py` on a real pipeline run (T1–T5) or by driving
> the real component the theorem names (T6 and T8–T15), not by assertion in
> prose.

Run it:

```bash
PYTHONPATH=. ./.venv/bin/python telos/tools/theorem_audit.py --cycles 40 --ci
```

Catalogued in code at `telos/core/verifier/theorem_audit.py::THEOREMS`.

---

## The audit table

| ID | Theorem | Measured metric | Passes when | Null (would falsify) | Null reachable by |
|----|---------|-----------------|-------------|----------------------|-------------------|
| **T1** | Determinism | sha256 fingerprint of two identically-seeded runs | fingerprints identical | fingerprints differ across identical seeds | config |
| **T2** | Process over Outcomes | `decision_integrity` per cycle | every DI ∈ [0, 1] | any cycle DI outside [0, 1] or missing | config |
| **T3** | Computational Conservation | `budget_consumed_ms / budget_total_ms` | max overrun ≤ 1.1× | any cycle consumes > 1.1× budget | config |
| **T4** | Possibility Preservation | `len(strategic_options)` per cycle | ≥ 1 alternative every cycle | a cycle stores zero alternatives | config |
| **T5** | Emergent Intelligence | activated streams per cycle | ≥ 2 streams every cycle | a cycle activates < 2 streams | config |
| **T6** | Kintsugi (System Memory) | matching vs unrelated intent after a recorded failure | matching blocked, unrelated passes, no-ledger passes | matching intent passes (failure logged, not integrated) | component_injection |
| **T7** | Delayed Causality | `h_eff = max(h, τ+1)` | `h_eff > τ` | `h_eff ≤ τ` for some config | implementation_mutation |
| **T8** | Identity Projection (F(I)) | real `IdentityProjectionGate` on mission-less, core-value-violating, and role-incompatible intents | inadmissible intents projected out; reflex admitted | an identity-inadmissible intent survives F(I) projection | component_injection |
| **T9** | Constraint Propagation | real `ConstraintValidator` → `Council` → `DecisionFirewall` on an out-of-bounds action | validator, council, and firewall all refuse | a constraint-violating action passes validation | component_injection |
| **T10** | Feedback Adaptation | `InfrastructureManager.observe()` risk tolerance across a failure cluster | risk tolerance falls | a failure cluster leaves every policy parameter unchanged | component_injection |
| **T11** | Path Dependency | `WorldLedger` semantic identity, identical state / different history | identities differ | identical states yield identical depth regardless of history | component_injection |
| **T12** | Maintenance vs Recovery | `InfrastructureManager` recovery mode across a failure cluster | recovery mode engages | a sustained failure cluster never triggers recovery | component_injection |
| **T13** | Option Decay | `SkillLibrary.prune()` / `reset_cycle()` tracked total | stale skills archived and restored, total conserved | pruning deletes a skill (tracked total drops) | component_injection |
| **T14** | Adaptive Capacity | `MissionPolicyManager.set_policy()` mission name + change log | swap recorded, mission name preserved | swap unrecorded and/or loses the mission name | component_injection |
| **T15** | Structural Resilience | `DecisionFirewall` on council-rejected and low-integrity proposals | both refused independently; clean proposal passes | a council-rejected or low-DI proposal passes the firewall | component_injection |

`null_reachable` is emitted as a machine-readable field on every row by
`run_audit()` and by the CLI, so the one non-configuration null (T7) is visible
in the output, not only in this prose.

### Measured baseline (2026-09-18, `--cycles 20`, standard mode)

```
T1-determinism            <fingerprint> == <fingerprint>                 PASS
T2-process                20/20 cycles in [0,1]                          PASS
T3-conservation           max overrun ratio=0.00 over 20 cycles          PASS
T4-possibility            min options=29                                 PASS
T5-emergent               min activated streams/cycle=3                  PASS
T6-kintsugi               matching blocked, unrelated passes             PASS
T7-delayed-causality      h_eff=5 > tau=0                                PASS
T8-identity-projection    projected_out=2/3 (mission/value/role)         PASS
T9-constraint-propagation validator+council+firewall blocked             PASS
T10-feedback-adaptation   risk_tolerance 0.300 -> 0.000                  PASS
T11-path-dependency       fresh='alpha' history='alpha_persistent_entity' PASS
T12-recovery-threshold    recovery_mode=True after 10 blocked cycles     PASS
T13-option-decay          tracked 3->3 (archived=3)->3                    PASS
T14-adaptive-capacity     mission=high_stakes, risk=0.1, logged=True     PASS
T15-structural-resilience council_rejection + low_integrity blocked      PASS

THEOREM AUDIT: PASS  (15/15 theorems hold)
null reachability: component_injection=9, config=5, implementation_mutation=1
```

---

## Set C — the 20 constructive theorems: what converted, what did not

`research/latent_cognition.md` §4 states 20 constructive theorems for the
**superseded v1 20-axiom** system. Each is disposed of here; nothing is
counted as falsifiable unless it has a reachable null.

**Already covered by T1–T7** (same claim, measured on the live runtime):
Thm 1 (Architecture Produces Outcomes → T1), Thm 2 (Process over Outcomes →
T2), Thm 6 (Kintsugi → T6), Thm 8 (Delayed Causality → T7), Thm 10 (State
Maintenance → T3), Thm 16 (Possibility Preservation → T4), Thm 19 (Emergent
Intelligence → T5), Thm 20 (System Memory → T6).

**Converted to new null-bearing invariants** (10 claims → 8 new theorems):

| Set C claim | New theorem | What was made measurable |
|---|---|---|
| Thm 4 Constraint Propagation | T9 | out-of-bounds action vs real validator/council/firewall |
| Thm 5 Feedback Loops | T10 | failure cluster → risk tolerance falls |
| Thm 7 Path Dependency | T11 | different history, identical state → different meaning |
| Thm 9 Maintenance vs Recovery | T12 | failure cluster → recovery mode |
| Thm 11 Option Decay | T13 | prune archives (not deletes); reset restores; total conserved |
| Thm 12 Adaptive Capacity | T14 | policy swap recorded, mission identity intact |
| Thm 13 Structural Inertia | T14 | the policy change is recorded in the audit trail |
| Thm 14 Identity Shapes Decisions | T8 (Set D) | real F(I) gate projects inadmissible intents out |
| Thm 15 Exploration vs Comfort | T10 | the feedback loop is driven and observed (adaptation branch) |
| Thm 17 Structural Resilience | T15 | council gate and firewall block independently |

**Left as contract / metric-definition (NOT counted):**
- **Thm 3 (Multi-Level Architecture)** — a design contract that the four
  levels are independently modifiable. There is no natural measurement whose
  failure mode is a property of intelligence; it would require an
  architectural-swap experiment, not a runtime invariant. Left as a contract.
- **Thm 18 (Local vs Global Optima)** — `MD = ||Predicted − Observed||; MD > 0
  implies a validator's local model diverges from reality`. This is the
  definition of the MD metric itself, not an independent prediction. Left as a
  metric definition.

Scope note (honest limit): **T8 measures the canonical `IdentityProjectionGate`
primitive.** The integrated select phase (`telos/core/phases/select.py:629`)
calls the weaker `CommitmentOptimizer.is_trajectory_admissible`, which only
checks core values and then **logs** an inadmissible selection rather than
projecting it out. End-to-end "an identity-inadmissible intent is never
selected" is therefore **not yet enforced** in the pipeline; T8 claims only the
primitive that does enforce it. The enforcement gap is left as an open issue,
not papered over.

---

## What this fixes (and what it does not)

**Fixed:** the tautology. Every theorem now has a reachable null, exercised by
`tests/core/test_theorem_audit.py` (config-reachable nulls are fed hostile
traces; component-reachable nulls are exercised by injecting sabotaged
components, which flips the row to FAIL).

**Honest limits:**
- T7's null is not reachable through configuration alone (the implementation
  computes `max(h, τ+1)` by construction); falsifying it requires mutating the
  implementation. This is now emitted in machine output as
  `null_reachable: "implementation_mutation"` rather than hidden in prose.
- T1–T5 measure the runtime's own traces. They detect regressions, not
  whether the metrics are the *right* metrics. That is the next layer of work
  (independent external reproduction — the D5 gate).

## Relationship to the axiom falsifier

- `telos/core/verifier/axiom_falsifier.py` attacks the **constitution**
  (42 axioms) by sabotaging each axiom's dependency — coverage 42/42.
- This document measures the **theorems** derived from the runtime — 15/15 hold.

Together they replace "green because nothing checked" with "green because an
adversary tried to make it red and failed."
