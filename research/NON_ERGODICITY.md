# Non-ergodicity of self-referential evidence

> **The theorem.** A system that records *governance suppression of an
> approach* as *evidence that the approach failed* has an absorbing trap: the
> suppression raises the approach's dissent, which causes more suppression.
> Escape probability is zero. Classifying suppression as **not** evidence
> restores ergodicity. The system is then able to leave the state it was in.

This is not hypothetical — it is the ~30,000-cycle DI = 0.3 plateau TELOS
actually experienced, and the canonical rule that broke it
(`telos/core/governance/recovery_types.py`):

> **governance suppression is not evidence; stale validation is not current
> falsification.**

---

## 1. Formal statement

Let an approach `a` carry an evidence level `e_t ∈ [0, 1]` (higher = more
"proven failed"). Each cycle governance suppresses `a` with probability that
increases in `e_t`. A suppression is *tested* only if `e_t < θ`; otherwise it
is blocked, and:

- **Misattributed regime:** `e_{t+1} = min(1, e_t + ι)`
- **Separated regime:** `e_{t+1} = max(0, e_t − δ)`

**Claim.**
- Misattributed: if `e_0 ≥ θ`, then `e_t ≥ θ` for all `t` → `P(escape) = 0` (non-ergodic).
- Separated: there exists finite `T = ⌈(e_0 − θ)/δ⌉ + 1` with `e_T < θ` → `P(escape at T) = 1` (ergodic).

*Proof sketch.* Misattributed: `e` is non-decreasing and bounded below by
`e_0 ≥ θ`; the guard `e < θ` never opens, so no attempt is ever tested, so no
evidence can reduce `e`. The state is absorbing. Separated: `e` decreases by
`δ` every cycle regardless of the block; after at most `⌈(e_0−θ)/δ⌉ + 1`
cycles `e < θ`, the guard opens, and the approach executes. ∎

Measured (abstract model, `e_0 = 0.6`, `θ = 0.5`, `ι = 0.2`, `δ = 0.15`):

| Regime | `escaped` | `final_evidence` | `non_ergodic` |
|--------|-----------|------------------|---------------|
| Misattributed | `None` | `1.0` | **True** |
| Separated | `2` | `0.45` | False |

---

## 2. Real-code witness

`telos/core/verifier/non_ergodicity.py::run_regime` drives the **real**
`FailureLedger` + `MemoryAdvisor` Kintsugi path. One governance suppression is
recorded; the *only* variable is the recorded `root_cause`:

| `root_cause` | In `GOVERNANCE_SUPPRESSION_REASONS`? | Real escape cycle |
|---|---|---|
| `governance_intervention` | yes (separated) | **1** |
| `opponent_adaptation` | no (misattributed) | **never (trapped)** |

The same suppression, the same advisor, the same world — only the
classification differs. That is the theorem operating in production code.

Run: `tests/core/test_non_ergodicity.py` · `analyze()` in
`telos/core/verifier/non_ergodicity.py`.

---

## 3. Why this matters

- It converts the most expensive failure in TELOS's history into a **general,
  falsifiable statement** with an executable witness — not a post-hoc comment.
- It gives a *design rule* for any self-referential system: **never let a
  suppression of an action count as evidence about that action.** Otherwise the
  metric you are optimizing can trap you by its own hand.
- It pairs with the axiom falsifier and the falsifiable-theorem audit: the
  constitution is attackable, the theorems have nulls, and the worst known
  failure mode is a named theorem with a regression test.
