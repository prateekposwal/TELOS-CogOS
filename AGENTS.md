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
- **Tests:** `PYTHONPATH=. python3 -m pytest tests/ -q --tb=short` (631 tests)
- **Gap scanner:** `PYTHONPATH=. python3 telos/tools/gap_scanner.py`
- **Dependency graph:** `python3 telos/tools/dependency_graph.py`

## Status (FINISH + SHIP — 2026-08-14)
- **631/631 tests passing** across 55 test files
- **31/31 self-audit checks passing**
- **42 axioms** across 6 layers — verified by AxiomProver every cycle and self-audit check [25]
- **KnowledgeGraph edge layer** (`telos/core/knowledge/graph.py`): typed/weighted `Edge` dataclass, activation spreads along edges (Λ4.7 Law of Attention and Trajectory), `bfs`/`dfs`/`find_path` traversal, edges serialized in checkpoints and served by `/api/knowledge`
- **KnowledgeLinker** (`telos/core/knowledge/links.py`): one canonical registry binding KnowledgeGraph ↔ TheoryGenealogy ↔ SCM; promotion hook auto-links every promoted theory to its knowledge nodes (Λ6.7)
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
# Dashboard
python3 telos/serve_dashboard.py

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
- Cross-session learning via ExperienceManager
- Distributed Council (multi-agent validation)
- Real-world tool integration
- Autonomous curiosity-driven exploration

## Session Handoff — 2026-08-14 (FINISH + SHIP)

### Current State
- Session mood: deliberate
- Shipped: KnowledgeGraph edge layer, KnowledgeLinker, SCM topological order, TheoryBuilder observe_outcome + genealogy live-wiring, honest dashboard (no fabrication), dead .bak removed, Kintsugi exception logging, conversation→theory feed, empty-handoff writer guard
- Axiom count: 42 (reconciled)

### Decisions Made
- Removed `telos/dashboard.html.bak` from git — dead backup; contained the deleted `generateDemoKnowledge()` fabrication; all functionality lives in `dashboard/js/*`
- Converted bare `except: pass` in `serve_dashboard.py` `end_headers` to logged Kintsugi handling
- Wired conversation turns into theory formation via `observe_conversation_outcome` (pipeline method + `telos_task.py` call)
- Guarded `write_handoff` against empty zero-cycle sessions (root cause of the 216-block bloat; tests must not regenerate handoffs)
- Collapsed 216 empty duplicated handoff blocks into this single current handoff
- Reconciled stale doc counts (469/482/529/581 → 631 tests across 55 files)

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: ship session (no pipeline cycles run)
