---
name: telos
description: Use ONLY when the user asks to invoke, query, or develop TELOS — the Cognitive Operating System (CogOS) at this repo. Do not use for general coding tasks.
---

# TELOS — Cognitive Operating System

TELOS is a 42-axiom CogOS at `~/dev/telos/`. Intelligence is defined by architectural axiom satisfaction, not task accuracy.


## Core Operating Principle (Architect Mandate, 2026-08-01)

Every TELOS invocation MUST honor these three rules — they are load-bearing:

1. **DONE vs LEFT is mandatory.** Every report/status/plan ends with an explicitly labeled
   `DONE (verified)` list and a `LEFT / TODO (verified)` list. Mixing done + pending without
   labels is a FAILURE.
2. **DONE means SHIPPED.** "Done" = verified AND committed/pushed/deployed/live. Uncommitted,
   unshipped, or not-live work goes in LEFT, never DONE.
 3. **PATTERN FIRST — the loop-breaker.** After ANY fix, name the pattern that would have
    prevented it and structuralize it (shared foundation / one canonical source / one rule).
    Fixing one instance of a recurring pattern without fixing the pattern = the fix is LEFT.
    If 3+ fixes share a root cause, the root cause is the real task.
 4. **VERIFY AS THE USER.** Verify on the real surface (live site / real device / what a user
    sees), not just the local file. A local-pass that fails for the user = the task is LEFT.

## Usage

Run the pipeline:
```
cd ~/dev/telos && make run        # uses .venv/bin/python when present
# or: PYTHONPATH=. ./.venv/bin/python telos_task.py
```

Run tests:
```
cd ~/dev/telos && make test-all   # uses .venv/bin/python when present
# or: PYTHONPATH=. ./.venv/bin/python -m pytest tests/ -v
```

Never invoke a bare `python3` for project work — on hosts where the first
`python3` on PATH lacks numpy/pytest, every subprocess dies. The project
canonicalizes on `sys.executable` internally; use `.venv/bin/python` to run it.

## Architecture

```
Pipeline (9 phases): PERCEIVE → STREAMS → SIMULATE → EVALUATE → SYNTHESIS → SELECT → COUNCIL → ACT → REFLECT
```

### Components

| Component | Path | Purpose |
|-----------|------|---------|
| Pipeline | `telos/core/runtime.py` | 7-phase reasoning engine |
| 4 Cognitive Streams | `telos/core/streams/implementations.py` | Reflex (1.0), Perception (0.9), Memory (0.7), Planning (0.5) |
| Council | `telos/core/council/base.py` | Blocking validators; DI/MD verdict |
| 4 Validators | `telos/core/council/validators.py` | Reality, Constraint, MemoryAdvisor, MissionDriftDetector |
| Governance | `telos/core/governance/` | TrustManager, ReadinessEngine, Firewall |
| InfraManager | `telos/core/infra_manager/` | Calibrator, FailureLedger, MissionPolicy, AuditController |
| Simulation | `telos/core/simulation.py` | CounterfactualEngine + StrategicOption |
| Ledger | `telos/core/ledger/` | WorldLedger, SkillLibrary, ExperienceManager |
| Transparency | `telos/audit/monitor.py` | decision_log.json + report |

### Debug Loop Guard (canonical rule for the agent/debugger layer)

`telos/core/debug/guard.py` makes load-bearing the three loop-breaking
patterns the GridWorld pipeline already enforces (Decision Firewall loop-trap
Λ3.1, EvidenceProvenanceValidator Λ2.3×Λ6.5). If a debugging session starts
stuttering — same intent, no progress — apply these:

1. **Acts over Intentions (Λ3.1)** — an "I will read/run/edit" that yields
   consecutive zero tool-calls is a no-action cycle, not a plan. Inject the
   missing act instead of narrating it again (`DebugLoopGuard.record_intent`).
2. **One Grounded Truth (Λ6.5)** — never restate a failure cause without
   citing the actual pytest/tool-output row it came from; an uncited claim is
   an unsupported hypothesis, scored 0 and auto-deprioritised
   (`DebugLoopGuard.score_claim`). Restating it twice = loop signal.
3. **Single Concern per Thread (Λ1.1, Λ4.6)** — one debug thread holds one
   failing test. Referencing assertion A while holding file B fires an
   explicit reconciliation (`DebugLoopGuard.check_concern`); the two do not
   share a workspace without a conflict line.

Self-check before reporting: if you can't name the tool output your claim
grounded on, you are looping — stop and ground.

### Key Axioms (42 total — subset shown)

1.1 Architecture Produces Outcomes (Pipeline is pure structural engine)
1.2 Process over Outcomes (DecisionTrace captures DI)
2.3 Kintsugi (failures stored as assets in FailureLedger)
3.1 Recovery Mode (tightens policy params on detected failure)
3.3 Option Decay (SkillLibrary prunes low-utility skills)
4.1 Identity Shapes Decisions (SemanticDepth 4-layer ladder)
4.3 Possibility Preservation (CounterfactualEngine generates alternatives)
4.6 Emergent Intelligence (no single stream is "I"; coordination = intelligence)

## Running

- `telos_task.py`: GridWorld navigation + local LLM explanations
- `run_demo.py`: Original GridWorld demo
- Tests: 2684 passing (verified on the current `main`)
