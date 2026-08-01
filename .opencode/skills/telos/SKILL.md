---
name: telos
description: Use ONLY when the user asks to invoke, query, or develop TELOS — the Cognitive Operating System (CogOS) at this repo. Do not use for general coding tasks.
---

# TELOS — Cognitive Operating System

TELOS is a 42-axiom CogOS at `/Users/prateekposwal/Desktop/Vrooom-computation/telos/`. Intelligence is defined by architectural axiom satisfaction, not task accuracy.


## Core Operating Principle (Architect Mandate, 2026-08-01)

Every TELOS invocation MUST honor these three rules — they are load-bearing:

1. **DONE vs LEFT is mandatory.** Every report/status/plan ends with an explicitly labeled
   `DONE (verified)` list and a `LEFT / TODO (verified)` list. Mixing done + pending without
   labels is a FAILURE.
2. **DONE means SHIPPED.** "Done" = verified AND committed/pushed/deployed/live. Uncommitted,
   unshipped, or not-live work goes in LEFT, never DONE.
3. **Pattern identification + gap filling.** When work is complete, scan for recurring patterns
   and structural gaps; propose or execute the fix that closes them. Do not stop at "task complete."

## Usage

Run the pipeline:
```
PYTHONPATH=/Users/prateekposwal/Desktop/Vrooom-computation python3 /Users/prateekposwal/Desktop/Vrooom-computation/telos_task.py
```

Run tests:
```
PYTHONPATH=/Users/prateekposwal/Desktop/Vrooom-computation python3 -m pytest tests/ -v
```

## Architecture

```
Pipeline (7 phases): PERCEIVE → STREAMS → SIMULATE → EVALUATE → SELECT → COUNCIL → ACT
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

### Key Axioms (20 total)

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
- Tests: 469/469 passing across 47 files
