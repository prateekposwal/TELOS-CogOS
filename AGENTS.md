# TELOS — Cognitive Operating System

## PROJECT MAP (authoritative — read first, every session)
Run `python3 telos/tools/session_start.py` at session start. It prints this map with live status.

| Project | Path | Status |
|---|---|---|
| **TELOS CogOS** | this workspace (`Vrooom-computation`) | 🟢 **ACTIVE** |
| **Bitcoin Block Space** (bitcoinsahi.com) | `../block-space-economics` (sibling) | 🟢 **ACTIVE** |
| **Trading Project** (skills/curriculum/Strategy Lab) | state in `TRADING_PROJECT_STATE.md` (this repo) | 🟡 **PARKED / INACTIVE** — resume conditions + full resumable state in that file |
| ~~Bitcoin Priority Oracle (v1)~~ | ~~`../bitcoin-priority-oracle`~~ | ⚫ **DEAD** — does not exist; never repoint anything to it. Its successor is `../block-space-economics`. |

**Session primer rule (prevents cross-project confusion):**
- The ACTIVE data/research project is `../block-space-economics` — NOT `bitcoin-priority-oracle` (v1 is dead).
- Do NOT mix trading-project work into block-space sessions, and vice-versa.
- `session_start.py` is the single source of truth for the project list — edit it there, not inline here.

## Quick Links
- **GitHub:** https://github.com/prateekposwal/TELOS-CogOS
- **Dashboard:** http://localhost:8765
- **Tests:** `PYTHONPATH=. python3 -m pytest tests/ -q --tb=short` (831 tests)
- **Gap scanner:** `PYTHONPATH=. python3 telos/tools/gap_scanner.py`
- **Dependency graph:** `python3 telos/tools/dependency_graph.py`

## Status (SHIPPED — v6.1 — 2026-08-20)
- **831 tests passing** (2 formerly-red dashboard DOM-contract tests repaired; 4 trace-schema contract tests; 6 v6 test files)
- **31/31 self-audit checks passing**
- **v6 modules wired & tested**: governance (`telos/core/governance/` — `governor.py`, `capability_authorization.py`), epistemic/evidence/acquisition (`telos/world/` — `epistemic.py`, `evidence.py`, `acquisition.py`), theory experiment (`telos/core/reasoning/theory/experiment.py`), 3 domain adapters (`dev_validation.py`, `logistics_simulator.py`, `robotics_simulator.py`), 3 benchmarks (`telos/benchmarks/` `devdomain_v61.py`/`logistics_v62.py`/`robotics_v70.py` with `main()` CLI + provenance result JSONs)
- **Decision trace schema contract**: canonical aliases `intent`/`discrimination_index`/`action_taken` + `budget_carryover_ms` in `to_dict()` (`telos/core/types.py`) — no consumer invents its own names (locked by `tests/core/test_trace_schema.py`)
- **EvidenceProvenanceValidator** (`telos/core/council/validators/evidence.py`): council advisor scoring candidate intents against the falsification record (RealityGapTracker + no-action history) — decision-provenance-as-evidence (Λ6.5)
- **Λ3.1 stagnation recovery**: consecutive no-action cycles arm goal-seek escape with recorded reason (`_update_stagnation_recovery_state` in `runtime.py`)
- **RealityGapTracker → CapabilityAuthorization feed**: per-model model_fidelity feeds the act-phase capability gate (`telos/core/phases/act.py`)
- **Legal-motion planner**: `legal_goal_step`/`legal_cardinal_action` in `telos_task.py` — A* cardinal-only first step so model and executor agree on what is reachable
- **42 axioms** across 6 layers — verified by AxiomProver every cycle and self-audit check [25]
- **KnowledgeGraph edge layer** (`telos/core/knowledge/graph.py`): typed/weighted `Edge` dataclass, activation spreads along edges (Λ4.7 Law of Attention and Trajectory), `bfs`/`dfs`/`find_path` traversal, edges serialized in checkpoints and served by `/api/knowledge`
- **KnowledgeLinker** (`telos/core/knowledge/links.py`): one canonical registry binding KnowledgeGraph ↔ TheoryGenealogy ↔ SCM ↔ **Identity nodes**; promotion hook auto-links every promoted theory to its knowledge nodes (Λ6.7)
- **SCM causal propagation** (`telos/core/reasoning/causal/scm.py`): Kahn topological order in `do()` — descendants recompute only after their causal parents settle
- **TheoryBuilder `observe_outcome`** (`telos/core/reasoning/theory/builder.py`): pipeline cycles AND conversation turns feed experience → pattern → hypothesis → theory (Λ6.5)
- **Genealogy live-wiring** (`telos/core/reasoning/genealogy.py`): `get_lineage`/`get_descendants` cycle-guarded; promoted theories register in `TheoryGenealogy` with parent lineage
- **Conversation → theory formation**: `observe_conversation_outcome` bridges the chat path in `telos_task.py` into TheoryBuilder
- **Honest dashboard**: `/api/knowledge` serves real serialized nodes AND edges; empty graph renders an honest empty state — no fabricated demo data; dead `dashboard.html.bak` (contained the deleted `generateDemoKnowledge()` fabrication) removed from git
- **Kintsugi exception handling**: bare `except: pass` in `serve_dashboard.py` `end_headers` → logged warning (Λ2.3, no silent swallows)
- **9-phase pipeline**: Perceive → Streams → Simulate → Evaluate → Synthesis → Select → Council → Act → Reflect
- **6 cognitive streams**: Reflex, Perception, Inquiry, Memory, Planning, Theory
- **Identity architecture**: 6-layer hierarchy (Core → Narrative → Mission → Project → Method → Action)
- **Unified Cognitive Functional**: 18-term J with aesthetic heuristic + project coherence
- **Benchmark framework**: 24 metrics across 7 cognitive processes, health dashboard
- **Resource Accounting**: R(a,s) = (C_compute, C_memory, C_bandwidth, C_storage)
- **Identity↔Knowledge wiring** (`telos/core/identity/identity_bridge.py`): IdentityBridge closes the identity island — mutable layers (IdentityNarrative/IdentityState) write provenance-stamped self-observation nodes to the identity domain via `KnowledgeGraph.record_internal` (trusted-caller gate), join the KnowledgeLinker as a 4th connected structure, and answer "what do I know about my own state?" (`pipeline.get_identity_knowledge()`). Frozen IdentityCore untouched (Λ4.1 × Λ4.10 × Λ6.7)
- **RNG isolation** (flake killed): one RNG authority per engine — simulators/engine/adapters/select-phase own private `RandomState`, never global `np.random` in production hot paths; seeded regression test locks the discrimination-collapse pattern dead
- **DistributedCouncil live** (`telos/core/council/distributed.py`): 5-agent advisory crew (PRIMARY/SKEPTIC/EXPLORER/CONSERVATIVE/ANALYST) re-scores primary council evidence through role lenses every cycle (configurable cadence + disable), aggregates weighted, surfaces in ctx/DecisionTrace/decision log — advisory only, primary blocking power untouched (Λ1.2)
## All shipping blockers cleared
- All 19 v2/v2.5 modules wired into pipeline
- KnowledgeGraph edge layer + cross-graph linker (KnowledgeGraph ↔ Genealogy ↔ SCM) shipped
- TheoryBuilder observe_outcome + live genealogy promotion shipped
- Honest dashboard (real serialized edges, no fabrication) shipped
- Conversation path feeds theory formation
- Empty handoff writer guard: `write_handoff` skips zero-decision/zero-cycle sessions (no bloat regeneration)
- Identity as projection operator (F(I) gate)
- Cross-session learning (agents_writer + agents_reader)
- Council deliberation loop (InternalDebate as primary mechanism)
- Resource Accounting Layer with enforcement
- Representational Ecology paper published
- Axiom count reconciled (genesis=42, AXIOMS.md=42)
- 7 large files split into packages (validators, simulation, theory, checkpoint, benchmarks, infrastructure, explanation)

## To run
```bash
# Dashboard (persistent launcher — survives terminal close; logs to /tmp/telos_dashboard.log)
./telos/start_dashboard.sh            # start (status / stop / restart subcommands)
# raw server (foreground) still works: python3 telos/serve_dashboard.py

# Pipeline
PYTHONPATH=. python3 telos_task.py

# Self-audit
PYTHONPATH=. python3 telos/tools/self_audit.py

# Benchmark demo
PYTHONPATH=. python3 -m telos.benchmarks.demo --cycles 10 --markdown

# Tests
PYTHONPATH=. python3 -m pytest tests/ -q
```

---

# TELOS — Future Roadmap

## Phase 1: Polish & Ship (Done)
- TelemetryCollector, OmegaThresholdLearner seeded, README with v2/v2.5 table
- Dashboard WebSocket, smoke tests for 19 modules
- GENESIS.md deduplication, VISION_v2.md status update
- AXIOMS.md reconciled (42 axioms)

## Phase 2: Core Architecture
- Rust migration
- macOS Voice Assistant ("Hey TELOS")
- ✅ ResourceGradientTracker reallocation loop
- ✅ Cross-session identity persistence via SystemSelf
- ✅ Council human-in-the-loop (HumanGateway)
- ~~MealDrama adapter~~ (archived)

## Phase 3: Long-term Vision
- ✅ Cross-session learning via ExperienceManager
- ✅ Distributed Council (multi-agent validation) — shipped 2026-08-14 as in-process advisory crew
- Real-world tool integration
- Autonomous curiosity-driven exploration

## Session Handoff — 2026-08-14 (FIX + LIVE-DATA + STORY + SHIP)

### Current State
- Session mood: deliberate
- Shipped: **live-data dashboard** — the dashboard now PRODUCES the data it serves. `DashboardProducer` (`telos/dashboard/producer.py`) runs the real GridWorld pipeline on a background thread inside `serve_dashboard.py`; one launcher command = one system that produces + serves + visualizes live data. Open http://localhost:8765 → story hero + three live graphs (Brain/Grid/Knowledge) visible on load, no tabs required.
- Live data verified: `/api/knowledge` returns real nodes AND edges (93 nodes / 1186 edges from the real pipeline run, incl. identity_affinity/follows/at_location), `/api/checkpoints` returns full serialized traces, `/api/health` shows cycles > 0 + real mood, `/api/overview` drives the big-data-story strip. WebSocket pushes lean traces + overview every cycle (fixed a double-module import that silently broadcast to an empty client set, and a 1MB frame overflow from heavy audit fields).
- Honesty restored: deleted `dashboard/js/demo.js` (fabricated 8 demo traces + Math.random values), removed the random-goal autopilot and random-importance KG node generation in `dashboard.js`. All numbers now measured or persisted — never invented.
- NaN JSON bug fixed: numpy scalars leak out of `DecisionTrace.to_dict()` → strict `json_clean` in the producer + `allow_nan=False` in `send_json`.
- Launcher hardened: `start_dashboard.sh` treats "running" as *the port answers* — zombies (kill -0 survivors) can no longer block a restart.
- Test count: 648 → 662 (14 new: 6 producer, 4 DOM-contract, 4 serve_dashboard API).

### Decisions Made
- Producer design: in-process background thread (option A from the fix brief) — one launcher = producer + HTTP + WebSocket. `TELOS_DASHBOARD_NO_PRODUCER=1` keeps the honest persisted-history fallback.
- Knowledge recording: the producer records REAL observations (DI per position, terrain encounters, rewards, council blocks) with `provenance caller=dashboard_producer`, plus edges (`follows` temporal chain, `at_location` terrain links) — the pipeline's own theory/identity nodes+edges also flow through.
- Legal-route executor: the pipeline's adapter emits diagonal/no-op vectors that `GridSim.transition` cannot route around blocked cells (agent stuck at origin). Producer decomposes the selected action into the best legal cardinal move (deterministic, respects genuine no-ops) — bounds-safe, verified in-bounds.
- WebSocket trace payload trimmed to the ~24 fields the frontend renders (full traces stay in `/api/checkpoints`, capped at 100).
- Verified as user: restart → curl probes → DOM-contract probe (70 targets, PASS) → headless Chromium render check (story populated, 3 canvases drawing, zero console/page errors, tabs still work) → WS push probe (traces + overview arrive live).

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: build+ship (live producer + visible graphs + story strip + 14 tests + headless-verified)

## Session Handoff — 2026-08-14 (EVOLVED + SHIPPED — the three gaps)

### Current State
- Session mood: deliberate
- Shipped: Identity↔Knowledge wiring (IdentityBridge), RNG isolation (flake dead across 5 consecutive full-suite runs), DistributedCouncil wired into the pipeline
- Axiom count: 42 (reconciled, unchanged)
- Test count: 631 → 648 (17 new tests: 8 identity-knowledge, 8 distributed-council, 1 RNG-isolation regression)

### Decisions Made
- **Gap 1 (identity↔knowledge, was 0/10)**: chose the provenance-gated safe write path — `KnowledgeGraph.record_internal()` is the ONLY way to write INTERNAL_DOMAINS, and only with trusted provenance (`caller=identity_bridge`). Identity joins the KnowledgeLinker as a 4th connected structure. Fixed a hidden dead block: `self._system_self` was never assigned (select-phase identity modeling silently died every cycle); also fixed two provenance-dropping serialization sites (`KnowledgeGraph.load`, checkpoint dump/load) the new audit trail exposed, plus linker rebind after checkpoint restore.
- **Gap 2 (latent flake)**: reproduced exactly (global seed 34 → all 5 GridWorld options at -0.9811497450761412). Root cause: simulator read shared global `np.random` whose state depends on test order. Fix: private `RandomState` per simulator/engine/adapter/select-phase; engine never falls back to global. Seeded the flaky test; added a regression test that poisons global state and proves discrimination still holds.
- **Gap 3 (shelved council)**: DistributedCouncil now runs every cycle (or every N via `distributed_council_interval`, disable-able via `distributed_council_enabled`). 5 role-agents re-score the primary verdict's signals through role lenses (skeptic weights dissent 1.6×, conservative enforces DI floor 0.5 + MD cap 1.5, explorer has Λ4.3 novelty path). Weighted-majority aggregation; advisory only — primary blocking power untouched. `PRIMARAY` typo fixed → `PRIMARY` (deprecated alias kept). Aggregate flows to ctx, DecisionTrace, decision log.
- RNG audit classification: fixed all production simulation/pipeline sites; left `telos_task.py` (interactive harness, not in pytest), `trajectory_sufficiency.py` (theorem-checker consumed only by its own test), `gridworld_demo.py` (imported nowhere), tests/* (input generation — with production RNG isolated, ordering cannot corrupt behavior).

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: build+ship session (3 gap closures + 17 tests + 5×648 green runs)

## Session Handoff — 2026-08-14 07:52:42

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 5


## Session Handoff — 2026-08-20 01:08:43

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.387 | Cycles: 2


## Session Handoff — 2026-08-20 01:09:59

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 3


## Session Handoff — 2026-08-20 01:28:46

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.600 | Cycles: 8


## Session Handoff — 2026-08-20 01:28:53

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.600 | Cycles: 8


## Session Handoff — 2026-08-20 01:29:30

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.600 | Cycles: 8


## Session Handoff — 2026-08-20 01:45:25

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 11


## Session Handoff — 2026-08-20 01:52:51

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 11


## Session Handoff — 2026-08-20 (EXECUTED FULL ROADMAP — COMPLETE v6 SHIP)

### Current State
- Session mood: deliberate
- Shipped: **the entire v6 roadmap, committed** — trace-schema aliases, dashboard test repair, stagnation recovery, RealityGap→Capability feed, evidence validator, 3 domain benchmarks, budget carryover telemetry, AGENTS.md map update
- Test count: 830 passing (100% green, verified 2026-08-20)

### Decisions Made
- **Trace schema lock** (`telos/core/types.py`): `to_dict()` emits canonical aliases `intent`/`discrimination_index`/`action_taken` + `budget_carryover_ms`; contract locked by `tests/core/test_trace_schema.py` — no consumer invents names (schema-drift pattern dead)
- **Λ3.1 stagnation recovery** (`telos/core/runtime.py`): `_update_stagnation_recovery_state` arms goal-seek escape after 3 consecutive no-action cycles with recorded reason `no_action_stagnation` — kills the `blended_inquiry` null-action loop pathology
- **EvidenceProvenanceValidator** (`telos/core/council/validators/evidence.py`): council advisor scores candidate intents against RealityGapTracker falsification record + intent-type no-action history; inquiry types never penalised; dissents force differently-typed escape (Λ6.5)
- **RealityGap→Capability feed** (`telos/core/phases/act.py`): act-phase reads `_reality_gap_tracker.model_fidelity()` — validated models <0.5 fidelity gate FAIL
- **Legal-motion planner** (`telos_task.py`): `legal_goal_step`/`legal_cardinal_action` A* cardinal-only first step keeps model and executor in agreement; GridSim/simulate use the same helpers
- **Benchmark orphans closed** (`telos/benchmarks/`): `devdomain_v61.py`/`logistics_v62.py`/`robotics_v70.py` each run via `python3 -m telos.benchmarks.<name>` with `main()` CLI and write provenance result JSONs
- **Dashboard tests repaired**: 2 formerly-red dashboard DOM-contract tests fixed — suite fully green
- **Gap-scanner guard fixed, not weakened** (`telos/tools/gap_scanner.py`): repo-root `telos_task.py` now in the reference universe (main-harness-only helpers were falsely flagged dead); dotted module refs resolve as packages; `post_execute` classified as a phase lifecycle dispatch hook. Ships with zero dead code — removed the unused `_coerce_status` helper (act.py) and the unimported `pipeline_helpers` dead module (runtime reimplements its logic as methods). Docstring Args hygiene added across staged v6 files so every check passes honestly (no `--no-verify`, no guard weakening)

### Open Issues
- *(None)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: build+ship session (6 logical commits)


## Session Handoff — 2026-08-21 (COORDINATED FIREWALL vs STAGNATION + SHIP)

### Current State
- Session mood: deliberate
- Shipped: **latent-bug fix b43bdaf** — coordinated the Λ3.1 no-action STAGNATION recovery with the action-loop FIREWALL so governor loops escape without breaking firewall traps. Dashboard live-trace feed also broadcasts `budget_carryover_ms`/`budget_consumed_ms` (75266c9).
- Test count: 831 passing (was 830) — 100% green; self-audit 31/31; working tree clean.

### Decisions Made
- **Root cause** (b43bdaf): the new STAGNATION recovery injected `goal_seek_recovery` onto inquiry-loop intents, inserting a different type into the firewall's action history and breaking its 4-consecutive same-type window before its own `RECOVERY_AFTER_LOOP_BLOCKS=2` streak — so `test_loop_recovery` failed (trap_cycles empty). And before that injection, governor no-action loops on non-inquiry types were armed but never escaped.
- **Fix — coordinate by intent-type intent, disjoint by construction**:
  - Exempt genuine inquiry-loop intents (`perceive`/`memory_miss`/`blended_inquiry`/`curiosity_explore`/...) from STAGNATION arming — their dwell is deliberate exploration (Λ6.5, mirrors the EvidenceProvenanceValidator exemption); the FIREWALL owns their repeat-trap escape (INV-1 restored: streak==2 blocks inject the escape).
  - Keep STAGNATION as the escape for NON-inquiry governor no-action loops (e.g. `plan_trajectory` with firewall==0 the whole run) — closes the original armed-but-never-injected bug (INV-2).
  - Exempt `goal_seek_recovery` from re-arming stagnation so a recovered cycle never immediately re-arms a second recovery.
- **Adds** `test_governor_no_action_loop_injects_stagnation_recovery`.

### Open Issues
- *(None)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: audit + ship session (coordinated-fix AGENTS.md reconciliation)
