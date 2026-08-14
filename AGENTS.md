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
- **Tests:** `PYTHONPATH=. python3 -m pytest tests/ -q --tb=short` (648 tests)
- **Gap scanner:** `PYTHONPATH=. python3 telos/tools/gap_scanner.py`
- **Dependency graph:** `python3 telos/tools/dependency_graph.py`

## Status (EVOLVED + SHIPPED — 2026-08-14)
- **648/648 tests passing** across 73 test files (5 consecutive green runs)
- **31/31 self-audit checks passing**
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

