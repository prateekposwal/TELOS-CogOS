# TELOS — A Cognitive Operating System

> *"An intelligent system is defined not by the number of visible capabilities it possesses, but by the invisible coordination of latent cognitive processes working toward a unified mission."*
>
> — The Principle of Latent Cognition (Axiom 4.6)

**TELOS is a formally axiomatized Cognitive Operating System (CogOS).** It is not a model, an agent, or a framework. It is a reasoning engine governed by 42 axioms across 6 architectural layers — designed to construct intelligent behavior from first principles.

## Quick Facts

| Metric | Value |
|--------|-------|
| **Axioms** | 42 across 6 layers (Architectural, Feedback, Adaptive, Emergent, Commitment, Cognitive Dynamics) |
| **Pipeline** | 9-phase: Perceive → Streams → Simulate → Evaluate → Synthesis → Select → Council → Act → Reflect |
| **Cognitive Streams** | 6 (Reflex, Perception, Memory, Planning, Theory, Inquiry) |
| **v2/v2.5 Modules** | 19 (CouncilReflector, TheoryBuilder, UnknownUnknownDetector, InternalDebate, etc.) |
| **Tests** | 428 passing across 46 files |
| **Self-audit** | 24/24 structural checks passing |
| **Resource Accounting** | R(a,s) = (C_compute, C_memory, C_bandwidth, C_storage) |
| **Unified Objective** | J(τ) = αU − βC_m − γC_r − δC_i − εC_align + ζG_theory + ηI_gain − θE_interpret + OP + CF − PE − C_o |

## Architecture

```text
PERCEIVE → STREAMS → SIMULATE → EVALUATE → SYNTHESIS → SELECT → COUNCIL → ACT → REFLECT
```

Each phase satisfies specific axioms:

| Phase | Axioms | Purpose |
|-------|--------|---------|
| PERCEIVE | 2.4, 4.1, 4.7 | Ingest state → build World → enrich with ledger history |
| STREAMS | 3.2, 4.2, 4.6 | Cognitive streams process World within budget |
| SIMULATE | 2.5, 4.3 | CounterfactualEngine generates alternative futures |
| EVALUATE | 1.2, 4.5 | Intents ranked by utility; local vs global optima |
| SYNTHESIS | 4.6 | Stream conflict resolution; intent merging |
| SELECT | 5.1 | Unified Cognitive Functional J(τ); Ω operator for inquiry |
| COUNCIL | 2.1, 4.4 | Validators check reality, constraints, history, drift |
| ACT | 1.1, 1.3 | Intent → action via domain adapter |
| REFLECT | 2.6, 6.5 | Meta-insight, pattern discovery, theory formation |

## Getting Started

```bash
# Run the pipeline
cd telos && PYTHONPATH=. python3 telos_task.py

# Run tests
PYTHONPATH=. python3 -m pytest tests/ -v

# Dashboard
python3 telos/serve_dashboard.py
```

## Repository Structure

| Directory | Contents |
|-----------|----------|
| `telos/` | TELOS CogOS — core architecture, axioms, pipeline, modules |
| `archive/` | Archived code (MealDrama adapter, old experiments) |
| `contracts/` | Domain model interfaces |
| *(root)* | (Bitcoin research archived — canonical home: [`../block-space-economics`](../block-space-economics)) |

## Bitcoin Research

The [Bitcoin State Pricing research](https://github.com/prateekposwal/block-space-economics) — the problem of UTXO set storage cost in Bitcoin — is owned by the sibling repo [`../block-space-economics`](../block-space-economics) (bitcoinsahi.com), its canonical home. TELOS does not maintain it here; legacy v1-era analysis snapshots live under `archive/`.

## License

Research use. See [CONTRIBUTING.md](telos/CONTRIBUTING.md) for details.
