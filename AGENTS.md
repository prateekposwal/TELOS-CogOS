# TELOS — Cognitive Operating System

## Quick Links
- **GitHub:** https://github.com/prateekposwal/TELOS-CogOS
- **Dashboard:** http://localhost:8765
- **Tests:** `PYTHONPATH=. python3 -m pytest tests/ --ignore=tests/test_knowledge.py -q`

## Status (Session Handoff — 2026-07-25)
- **469/469 tests passing**
- **24/24 self-audit checks passing**
- **Ω operator** with adaptive threshold + continuous sigmoid blend
- **Tripartite uncertainty** U = (U_W, U_I, U_O)
- **Relational Reasoning scaffold** (R_t slot reserved, interface defined)
- **3D isometric GridWorld** dashboard with orbit/zoom/click controls
- **12 Bitcoin-inspired upgrades** — UTXO traces, Merkle proofs, PSDT, timelocks, SegWit split, checkpoint chain, difficulty adjustment, voting thresholds, mempool, attention auction, halving, constraint opcodes
- **Deterministic execution** — cycle-aware seeding for reproducible runs
- **Curiosity Drive** — intrinsic motivation via learning progress + boredom detection
- **5 GridWorld upgrades** — Dynamic terrain, Fog of war, Multiple goals, Time pressure, Second agent
- **197 Python files, 35,000+ lines, 61 git commits**

## All shipping blockers fixed
- ✅ Firewall loop detection tuned (3→4 threshold, available_moves check)
- ✅ ExperienceManager threshold lowered (0.5→0.1), warm-up on startup
- ✅ Recovery mode timeout (20-cycle max auto-exit)
- ✅ 5 failing tests fixed (KG domain allowlist + score clamping)
- ✅ Ollama fallback (3 retries → graceful message)
- ✅ Learning loop primed (prime_skill_library on startup)

## To run
```bash
# Dashboard
cd /Users/prateekposwal/Desktop/Vrooom-computation && python3 telos/serve_dashboard.py

# Pipeline
cd /Users/prateekposwal/Desktop/Vrooom-computation && PYTHONPATH=. python3 telos_task.py

# Self-audit
cd /Users/prateekposwal/Desktop/Vrooom-computation && PYTHONPATH=. python3 telos/tools/self_audit.py
```

## Session Handoff — 2026-07-25

### Bitcoin / LinkedIn Content Project (NEW SESSION)

We discussed creating a **Bitcoin Block Priority Oracle** — a sidecar protocol for mining pools to prioritize financial transactions over data inscriptions. The user wants to continue this in a **separate session** with a fresh context.

**Key idea:** A lightweight oracle + Stratum v2 plugin that classifies transactions as "financial" vs "data" and creates a priority fee market without any consensus change.

**Conversation reference:** The user asked about tech stack (Rust/Go + Stratum v2), resources needed (2-3 people, 8-10 weeks), and wants a LinkedIn post series starting with this architecture.

**To start the new session, prompt with:**
> "Continue Bitcoin Block Priority Oracle project from AGENTS.md handoff. Build the tech architecture doc and draft the first LinkedIn post."

---

# TELOS — Future Roadmap (Post-Ship)

### ✅ Phase 1: Polish & Ship (Done)
- ✅ Wire TelemetryCollector to actually record
- ✅ Seed OmegaThresholdLearner with more buckets (11 buckets, weak synthetic priors)
- ✅ Write production README and API docs (v2/v2.5 module table, 422 test count)
- ✅ Add Dashboard WebSocket health check
- ✅ Smoke tests for all 19 v2/v2.5 modules (62 tests, 422 total)
- ✅ GENESIS.md deduplication + VISION_v2.md status update

### Phase 2: Core Architecture
- Rust migration — core pipeline rewrite
- macOS Voice Assistant ("Hey TELOS")
- ✅ Activate ResourceGradientTracker reallocation loop
- ✅ Cross-session identity persistence via SystemSelf
- ✅ Council human-in-the-loop escalation (HumanGateway wired in act.py)
- ~~MealDrama adapter~~ (archived per architect's instruction)

### Phase 3: Long-term Vision
- Cross-session learning via ExperienceManager (longitudinal persistence)
- Distributed Council (multi-agent validation)
- Real-world tool integration (Calendar, Files, APIs)
- Autonomous curiosity-driven exploration

## Session Handoff — 2026-07-25 03:26:27

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0 | Token budget: 0.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0030.json

## Session Handoff — 2026-07-26 15:11:51

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0 | Token budget: 0.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0030.json


## Session Handoff — 2026-07-27 19:34:56

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0


## Session Handoff — 2026-07-27 19:34:56

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0


## Session Handoff — 2026-07-27 19:34:56

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0


## Session Handoff — 2026-07-27 19:42:24

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0


## Session Handoff — 2026-07-27 19:42:24

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0


## Session Handoff — 2026-07-27 19:42:24

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0


## Session Handoff — 2026-07-27 20:08:56

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0


## Session Handoff — 2026-07-27 20:08:56

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0


## Session Handoff — 2026-07-27 20:08:56

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0


## Session Handoff — 2026-07-27 22:05:43

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0


## Session Handoff — 2026-07-27 22:05:43

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0


## Session Handoff — 2026-07-27 22:05:43

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0

