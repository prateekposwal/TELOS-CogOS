# MealDrama — APK Build Workflow

## Build Pipeline
```
npm run build           → Vite bundles React/TS → static HTML+JS+CSS in dist/
rsync -a dist/ → android/app/src/main/assets/public/   → Copy to Android
./gradlew assembleDebug → Build APK with bundled assets
```

## Quick APK rebuild (after code changes)
```bash
npm run build
export JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-25.jdk/Contents/Home
rsync -a /Users/prateekposwal/MD-App/dist/ /Users/prateekposwal/MD-App/android/app/src/main/assets/public/
cd /Users/prateekposwal/MD-App/android && ./gradlew assembleDebug
```

**Key detail:** `npm run build` must run first every time. Without it, the APK contains stale web assets. Vite tree-shakes, minifies, chunks (vendor/icons/dishes), applies Tailwind, and generates Brotli-compressed `.br` files alongside the originals.

## Where the APK lands
```
/Users/prateekposwal/MD-App/android/app/build/outputs/apk/debug/app-debug.apk
```

## Architecture
- **Frontend:** Vite + React 19 + Tailwind 4 (web app)
- **Mobile wrapper:** Capacitor 8 (fullscreen WebView, wraps the web app as native APK)
- **Not React Native** — RN migration is Sprint D (future work)
- **State:** Zustand with localStorage persistence + PostgreSQL via Prisma

---

# TELOS — Future Roadmap (Post-Rust Migration)

## Planned Work (not today — after Rust migration)

### 1. Rust Migration
- Rewrite TELOS core pipeline (7 phases, streams, council, governance) in Rust
- Keep Python bindings for LLM integration (via PyO3 or subprocess)
- Target: performance improvement, lower memory footprint, single binary distribution

### 2. macOS Voice Assistant ("Hey TELOS")
- **Wake word**: Porcupine or offline wake word engine → triggers TELOS
- **Speech-to-text**: macOS NSSpeechRecognizer or local Whisper
- **Pipeline**: Voice → text → TELOS pipeline → text → speech via macOS `say`
- **Tool integration**: Calendar, Reminders, Files, Terminal, MealDrama API
- **Daemon**: Run TELOS as a background launchd service
- **Container**: TELOS as the cognitive container with pluggable tool registry

### 3. TELOS Dashboard Enhancements
- Real-time 3D terrain visualization (DI/MD chart)
- Chat panel with command history
- Live WebSocket trace feed
- Authentication (JWT with device ID)

### 4. Knowledge Systems
- Unlock ALLOWED_WRITE_DOMAINS (already configured)
- ExperienceManager skill indexing
- Cross-session preference learning

### 5. Model
- Current: phi3:mini (Microsoft, 3.8B, local via Ollama)
- Evaluated alternatives: Llama 3.2, Mistral, Phi-3
- All run 100% locally — no data leaves the machine

## Session Handoff — 2026-07-23 02:16:43

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.901 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0035.json

## Session Handoff — 2026-07-23 02:18:04

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 2.182 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0036.json

## Session Handoff — 2026-07-23 02:19:47

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.838 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0037.json

## Session Handoff — 2026-07-23 02:21:40

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.922 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0038.json

## Session Handoff — 2026-07-23 02:24:29

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 2.020 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0039.json

## Session Handoff — 2026-07-23 02:26:36

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.922 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0040.json

## Session Handoff — 2026-07-23 02:32:43

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 1.951 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0041.json

## Session Handoff — 2026-07-23 02:35:47

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 1.414 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0042.json

## Session Handoff — 2026-07-23 02:58:01

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 3.588 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0046.json

## Session Handoff — 2026-07-23 02:58:45

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 2.377 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0047.json

## Session Handoff — 2026-07-23 03:04:33

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 2.302 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0048.json

## Session Handoff — 2026-07-23 03:21:45

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 5.072 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0049.json

## Session Handoff — 2026-07-23 03:23:17

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.975 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0050.json

## Session Handoff — 2026-07-23 03:26:48

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.749 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0051.json

## Session Handoff — 2026-07-23 03:56:38

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 5.657 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0053.json

## Session Handoff — 2026-07-23 03:57:19

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.897 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0054.json

## Session Handoff — 2026-07-23 03:59:01

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 2.237 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0055.json

## Session Handoff — 2026-07-23 04:02:26

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 5.657 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0057.json

## Session Handoff — 2026-07-23 04:03:10

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.860 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0058.json

## Session Handoff — 2026-07-23 04:04:19

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.803 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0059.json

## Session Handoff — 2026-07-23 04:05:57

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.961 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0060.json

## Session Handoff — 2026-07-23 04:13:09

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.943 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0062.json

## Session Handoff — 2026-07-23 04:15:00

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.864 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0063.json

## Session Handoff — 2026-07-23 09:54:11

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.870 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0064.json

## Session Handoff — 2026-07-23 10:59:41

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 2.245 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0066.json

## Session Handoff — 2026-07-23 14:33:12

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 2.205 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0067.json

## Session Handoff — 2026-07-24 01:14:06

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 5.016 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0070.json

## Session Handoff — 2026-07-24 01:14:56

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.866 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0071.json

## Session Handoff — 2026-07-24 01:15:41

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.835 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0072.json

## Session Handoff — 2026-07-24 01:15:58

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 5.004 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0073.json

## Session Handoff — 2026-07-24 01:16:08

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 2.112 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0074.json

## Session Handoff — 2026-07-24 01:16:38

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.810 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0075.json

## Session Handoff — 2026-07-24 02:18:53

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 5.050 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0076.json

## Session Handoff — 2026-07-24 02:19:16

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.743 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0077.json

## Session Handoff — 2026-07-24 02:19:26

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.942 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0078.json

## Session Handoff — 2026-07-24 02:19:55

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 2.128 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0079.json

## Session Handoff — 2026-07-24 02:20:07

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.952 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0080.json

## Session Handoff — 2026-07-24 02:20:22

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 5.054 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0081.json

## Session Handoff — 2026-07-24 02:32:37

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 3.717 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0082.json

## Session Handoff — 2026-07-24 02:32:55

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 3.302 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0083.json

## Session Handoff — 2026-07-24 14:18:01

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.879 | Cycles: 1 | Token budget: 18.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0094.json

## Session Handoff — 2026-07-24 17:38:18

### Current State
- Working on: advance one unit in the specified direction without encountering obstacles and maintain a direct line of sight towards the user's goal
- Working on: carefully navigate while avoiding potential hazards, adhering to established protocols due to 'established_relationship', and following predictive models for future movement
- User preference: straight path towards goal
- Session mood: positive

### Decisions Made
- move right
- move up
- move down

### Open Issues
- *(No open issues)*

### Metrics
- DI: 0.300 | MD: 2.286 | Cycles: 5 | Token budget: -35.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0007.json

## Session Handoff — 2026-07-24 19:18:30

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.808 | Cycles: 1 | Token budget: 15.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0011.json

## Session Handoff — 2026-07-24 19:18:37

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.645 | Cycles: 1 | Token budget: 15.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0012.json

## Session Handoff — 2026-07-24 19:50:09

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.953 | Cycles: 1 | Token budget: 15.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0013.json

## Session Handoff — 2026-07-24 19:50:20

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.949 | Cycles: 1 | Token budget: 15.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0014.json

## Session Handoff — 2026-07-24 19:50:28

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.923 | Cycles: 1 | Token budget: 15.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0015.json

## Session Handoff — 2026-07-24 19:50:43

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 3.312 | Cycles: 1 | Token budget: 15.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0016.json

## Session Handoff — 2026-07-24 19:50:53

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.911 | Cycles: 1 | Token budget: 15.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0017.json

## Session Handoff — 2026-07-24 19:51:04

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.740 | Cycles: 1 | Token budget: 15.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0018.json

## Session Handoff — 2026-07-24 19:51:13

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.923 | Cycles: 1 | Token budget: 15.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0019.json

## Session Handoff — 2026-07-24 19:51:35

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 4.857 | Cycles: 1 | Token budget: 15.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0020.json

## Session Handoff — 2026-07-24 23:48:16

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0 | Token budget: 0.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0029.json

## Session Handoff — 2026-07-25 00:26:39

### Current State
- Session mood: neutral

### Decisions Made
- *(No decisions recorded)*

### Open Issues
- *(No open issues)*

### Metrics
- DI: 1.000 | MD: 0.000 | Cycles: 0 | Token budget: 0.0%

### Checkpoint
- /tmp/telos_checkpoints/checkpoint_0029.json

## Session Handoff — 2026-07-25 00:48:55

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

