# The live-loop plateau — what it was, what remains

Investigation of the reported `[4,2]` governor `risk_coverage` limit cycle in
the live GridWorld loop, run against the current kernel.

## Finding 1 — the described `risk_coverage` deadlock is already gone

The original plateau was an act-phase catastrophe veto: a fixed `4.0` MD bar
below the 5×5 grid's own corner-to-corner diameter (~5.66) vetoed healthy
horizon landings as `risk_coverage` catastrophes. That bar is now **scaled from
the simulator's declared world extent** (`act.py`: `(world_extent-1)·√n_dims` →
5.657 for GridSim).

Reproduction (200 real GridWorld cycles): **0 `risk_coverage` blocks.** The
governance blocks that remain are `action_loop` and `low_integrity` only.
A regression test asserts this stays gone
(`tests/core/test_inquiry_dwell.py::test_no_risk_coverage_plateau_in_real_run`).

## Finding 2 — what actually remains: high-duty inquiry dwell

The current pattern is **not a deadlock** — it is a high-dwell limit cycle:

| Metric | Measured (200 cycles, baseline) |
|---|---|
| no-op cycles (`selected_action` is None) | ~70% |
| max consecutive no-op streak | 8 (bounded — not unbounded) |
| episodes completed | 6 |
| selection mix | `blended_inquiry` + `curiosity_explore` ≈ **87%** |
| governance blocks | `action_loop` 22, `low_integrity` 23 (~30%) |

Inquiry types are exempt from the short stagnation threshold (their dwell is
deliberate exploration, Λ6.5), and the firewall's loop detector keys on the
*same action*. Because two inquiry types alternate
(`blended_inquiry ↔ curiosity_explore`), each clears the firewall's
same-action window, so the agent can dwell without action.

## Fix shipped — bounded inquiry dwell

`INQUIRY_DWELL_BUDGET = 6`. A type-agnostic consecutive-no-action counter now
increments every no-action cycle; after the budget, the goal-seek backstop arms
**even for inquiry types** (`_recovery_reason = "inquiry_dwell_budget"`). The
firewall still owns true same-action traps (it fires at 2) — an `action_loop`
block resets the backstop counter so it can never race the firewall.

Tests: `tests/core/test_inquiry_dwell.py` (5) — arms only after the budget,
alternation cannot evade it, action resets it, `action_loop` does not trigger
it, and no `risk_coverage` plateau.

## Honest limits (LEFT)

- The backstop **bounds** the dwell but does not eliminate the throughput cost:
  the A/B shows ~70% no-op either way. It is a safety floor, not a speedup.
- The decisive lever is **selection priority**: inquiry out-selects executable
  mission intents ~87% of the time. Rebalancing that scoring is a larger,
  riskier change to the select/J path and was deliberately **not** attempted
  here (the plateau is a labelled, non-critical pattern; DI stays 1.0 and
  episodes complete).
- Next precision step: instrument per-intent selection scores and test whether
  a mission-progress term (executable-intent availability) should outrank
  inquiry when the agent is not genuinely uncertain.
