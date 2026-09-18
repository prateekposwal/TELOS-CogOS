#!/usr/bin/env python3
"""TELOS v7 stability-gate endurance harness.

Runs a REAL pipeline (fast mode: real runtime, streams, validators, governor,
firewall, evidence, KnowledgeGraph, checkpointer — no stubs) for N cycles and
asserts every v7 stability invariant. This is the machine-run of the frozen
kernel: the result table is the official baseline for the next generation.

Invariants asserted (each with focused unit/regression coverage in
tests/core/test_endurance_invariants.py):
  1. DI stability     — final-window mean DI not frozen in a low plateau;
                        self-heal not pathologically re-triggered.
  2. Memory stability — own-process RETENTION is flat: the late-window slope of
                        retained pymalloc blocks (`sys.getallocatedblocks`) and
                        the absolute RSS envelope are both one-sided bounded.
                        Raw RSS drift is reported but NOT gated: it measures the
                        allocator/OS high-water, not TELOS retention.
  3. RNG stability    — global RNG scanner re-run = 0 hits; fixed-seed
                        determinism of short runs.
  4. Firewall stability — every block is a known type; loop traps escape via
                        designed machinery (no new infinite traps).
  5. Trace retention  — telemetry ring ≤ 200 (oldest dropped).
  6. KG retention     — node/edge caps hold; adjacency symmetric; oldest pruned.
  7. Checkpoint       — mean save < 100ms; retention ≤ 10; hmac chain links
                        across sparse numbering.
  8. Axiom integrity  — AXIOMS.md never re-read during the run; 42 intact;
                        fingerprint stable.
  9. Stagnation recovery — arming classified per the canonical exempt sets
                        (no false-positive escapes when actions flow).
 10. Load guard       — load-sensitive checks (memory_stability,
                         checkpoint_latency) report SKIPPED under host
                         contention, never a false PASS/FAIL. Threshold from
                         os.getloadavg()/cpu_count (plus swap pressure); see
                         LOAD_GUARD. Override with --force / --ignore-load
                         (env TELOS_ENDURANCE_IGNORE_LOAD=1) to demand a real
                         measurement; --strict exits 2 when a skip occurs.
"""
import argparse
from collections import deque
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time

import numpy as np

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)
logging.basicConfig(level=logging.CRITICAL)
logging.disable(logging.CRITICAL)

from telos_task import GridAdpt, GridSim, DEFAULT_BLOCKED, DEFAULT_REWARDS  # noqa: E402
from telos.core.runtime import PipelineConfig, TelosV14Pipeline  # noqa: E402
from telos.core.streams.implementations import (  # noqa: E402
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream, TheoryStream,
)
from telos.core.streams.inquiry_stream import InquiryStream  # noqa: E402
from telos.core.council.validators import (  # noqa: E402
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
    EvidenceProvenanceValidator,
)
from telos.core.ledger.skill_library import SkillLibrary  # noqa: E402
from telos.core.simulation import CounterfactualEngine  # noqa: E402
from telos.core.trace_builder import DecisionTrace  # noqa: E402

STABILITY = {
    "di_floor": 0.5,            # final-window mean DI must exceed this
    "rng_global_hits": 0,
    "trace_ring_cap": 200,
    "checkpoint_mean_ms": 100.0,
    "checkpoint_max_files": 10,
    "kg_edges_total_cap": 10000,
    "kg_edges_per_type_cap": 2000,
    "axioms": 42,
    "rss_drift_frac": 0.10,     # legacy RSS drift — REPORTED ONLY (noisy: the
                                # endpoint swings ±20% run-to-run under load)
    "rss_ceiling_kb": 300 * 1024,   # own-process RSS absolute envelope: a
                                    # runaway-native-growth guard, NOT a tight %
                                    # on a noisy endpoint
    "leak_blocks_per_cycle": 1.0,   # retained pymalloc blocks/cycle in the late
                                    # window (>1 ≈ 10k retained objects/run = a
                                    # real leak; bounded caches converge below)
    "max_trap_streak": 50,      # no infinite trap: longest consecutive
                                # action_loop-block streak must stay bounded
                                # (the Λ3.1 escape injects well before this)
}

# ── Load guard ────────────────────────────────────────────────────────────
# A gate that reports FAIL when the *machine* is loaded is measuring the
# machine, not TELOS. When the host is contended, the load-sensitive checks
# (memory retention + checkpoint timing) report SKIPPED with the measured load
# as evidence instead of a false FAIL. Override with --force / --ignore-load.
#
# Signals (all read live, never fabricated):
#   * os.getloadavg()[0] — the 1-minute kernel run-queue average (POSIX),
#     normalised by os.cpu_count() → "load per CPU". This is the primary gate.
#   * swap usage — `sysctl -n vm.swapusage` on darwin, /proc/meminfo on Linux.
#     Memory pressure directly corrupts the memory-retention measurement.
#   * competing heavy processes — `ps -A -o pcpu=` counted at pcpu>=25.
#     Reported as evidence only; not a gate (transient, noisy).
LOAD_GUARD = {
    "max_load_per_cpu": 0.75,   # 1-min loadavg / cpu_count
    "max_swap_frac": 0.70,      # swap_used / swap_total: >70% in use means the
                                # host is under memory pressure, which
                                # contaminates the retention measurement and
                                # contends with checkpoint disk I/O.
}
LOAD_SENSITIVE_CHECKS = ("memory_stability", "checkpoint_latency")


def _read_swap_mb() -> tuple:
    """Return (used_mb, total_mb) for swap, or (0, 0) if unreadable.

    darwin: `sysctl -n vm.swapusage` -> "total = 5120.00M  used = 4590.88M ...".
    linux: /proc/meminfo SwapTotal/SwapFree in kB.
    """
    try:
        if sys.platform == "darwin":
            out = subprocess.check_output(
                ["sysctl", "-n", "vm.swapusage"], text=True, timeout=5)
            # "total = 5120.00M  used = 4590.88M  free = 529.12M (encrypted)"
            import re
            mt = re.search(r"total\s*=\s*([\d.]+)M", out)
            mu = re.search(r"used\s*=\s*([\d.]+)M", out)
            return (int(float(mu.group(1))) if mu else 0,
                    int(float(mt.group(1))) if mt else 0)
        with open("/proc/meminfo") as f:
            kv = {}
            for line in f:
                k, _, v = line.partition(":")
                kv[k.strip()] = v.strip()
        total = int(kv.get("SwapTotal", "0 kB").split()[0]) / 1024.0
        free = int(kv.get("SwapFree", "0 kB").split()[0]) / 1024.0
        return (int(total - free), int(total))
    except Exception:
        return (0, 0)


def _count_heavy_procs(threshold: float = 25.0) -> int:
    """Competing CPU-heavy processes at >= threshold% CPU (informational)."""
    try:
        out = subprocess.check_output(
            ["ps", "-A", "-o", "pcpu="], text=True, timeout=5)
        return sum(1 for line in out.splitlines()
                   if line.strip() and float(line.strip()) >= threshold)
    except Exception:
        return 0


def read_load() -> dict:
    """Read the live host-load signals (see LOAD_GUARD for provenance)."""
    try:
        la = os.getloadavg()
    except (OSError, AttributeError):
        la = (0.0, 0.0, 0.0)
    cpus = os.cpu_count() or 1
    used_mb, total_mb = _read_swap_mb()
    return {
        "load1": round(la[0], 2),
        "load5": round(la[1], 2),
        "load15": round(la[2], 2),
        "cpus": cpus,
        "load_per_cpu": round(la[0] / cpus, 3),
        "swap_used_mb": used_mb,
        "swap_total_mb": total_mb,
        "swap_frac": round(used_mb / total_mb, 3) if total_mb else 0.0,
        "heavy_procs": _count_heavy_procs(),
    }


def load_reason(load: dict, guard: dict = None) -> str:
    """Return the human-readable reason the host is loaded, or "" if quiet.

    Pure predicate over a read_load() dict so it is directly unit-testable
    with os.getloadavg patched.
    """
    g = guard or LOAD_GUARD
    reasons = []
    lpc = float(load.get("load_per_cpu", 0.0))
    if lpc >= g["max_load_per_cpu"]:
        reasons.append(
            f"1-min load/cpu {lpc} >= {g['max_load_per_cpu']} "
            f"(load1={load.get('load1')} cpus={load.get('cpus')})")
    sf = float(load.get("swap_frac", 0.0))
    if sf >= g["max_swap_frac"]:
        reasons.append(
            f"swap {sf:.0%} >= {g['max_swap_frac']:.0%} "
            f"({load.get('swap_used_mb')}/{load.get('swap_total_mb')}MB)")
    return "; ".join(reasons)


def current_rss_kb() -> int:
    try:
        out = subprocess.check_output(
            ["ps", "-o", "rss=", "-p", str(os.getpid())], text=True)
        return int(out.strip())
    except Exception:
        return 0


def memory_leak_metrics(samples: list, cycles: int) -> dict:
    """Robust, one-sided leak estimate from post-warmup own-process memory.

    The previous measure compared a single final RSS sample against the window
    median. That is dominated by OS/allocator high-water behaviour under
    concurrent load: identical code swung from +3.8% (committed baseline) to
    +13.8% (failing run) to -19.7% (a re-run) with no code change — it was
    measuring the allocator, not TELOS. This measures the pipeline's *retained*
    allocations instead (`sys.getallocatedblocks`, the pymalloc block count —
    immune to allocator-arena/swap noise) and looks for a *sustained* late-window
    growth rate, so bounded caches that fill to their Lambda4.7 caps early do not
    read as leaks. Raw RSS is kept as a bounded absolute envelope.

    Args:
        samples: list of {i, rss_kb, blocks} post-warmup samples.
        cycles: total cycle count of the run.

    Returns:
        dict of warm/end block counts, late-window slope (blocks/cycle),
        projected growth fraction, and the reported RSS figures.
    """
    if not samples:
        return {"warm_blocks": 0, "end_blocks": 0, "leak_blocks_per_cycle": 0.0,
                "alloc_growth_frac": 0.0, "rss_end_kb": 0, "rss_idle_kb": 0,
                "rss_drift_frac": 0.0}
    xs = np.array([s["i"] for s in samples], dtype=float)
    blocks = np.array([s["blocks"] for s in samples], dtype=float)
    rss = np.array([s["rss_kb"] for s in samples], dtype=float)
    warm_mask = xs < cycles / 2.0
    warm = blocks[warm_mask] if warm_mask.any() else blocks
    warm_med = max(float(np.median(warm)), 1.0)
    # Late window (last 40% of the run): bounded caches have already filled by
    # then, so a positive slope is sustained retention growth = a leak.
    late_mask = xs >= cycles * 0.6
    slope = (float(np.polyfit(xs[late_mask], blocks[late_mask], 1)[0])
             if int(late_mask.sum()) >= 2 else 0.0)
    end_mask = xs >= cycles * 0.8
    end_med = (float(np.median(blocks[end_mask])) if end_mask.any()
               else float(blocks[-1]))
    rss_idle = float(np.median(rss))
    return {
        "warm_blocks": int(warm_med),
        "end_blocks": int(end_med),
        "leak_blocks_per_cycle": round(slope, 4),
        "alloc_growth_frac": round((slope * cycles) / warm_med, 6),
        "rss_end_kb": int(rss[-1]),
        "rss_idle_kb": int(rss_idle),
        "rss_drift_frac": round((float(rss[-1]) - rss_idle) / max(rss_idle, 1.0), 4),
    }


def build_pipeline(cp_dir: str, seed: int = 42, fast: bool = True) -> TelosV14Pipeline:
    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
    pipe = TelosV14Pipeline(PipelineConfig(
        adapter=GridAdpt(), simulator=sim,
        compute_budget_ms=100.0, state_dim=2, n_worlds=4, horizon=5,
        checkpoint_path=cp_dir, checkpoint_every_n=20,
        knowledge_path=os.path.join(cp_dir, "kg.json"),
        ledger_path=os.path.join(cp_dir, "ld.json"),
        identity_path=os.path.join(cp_dir, "id.json"),
        pattern_path=os.path.join(cp_dir, "pt.json"),
        deterministic_seed=seed, mode="fast" if fast else "standard",
    ))
    sl = SkillLibrary()
    for s in [ReflexStream(sl), PerceptionStream(sl), MemoryStream(sl),
              PlanningStream(sl, sim_engine=CounterfactualEngine(sim)),
              InquiryStream(sl),
              TheoryStream(sl, theory_builder=getattr(pipe, "_theory_builder", None))]:
        pipe.register_stream(s)
    for v in [RealityValidator(), ConstraintValidator(), MemoryAdvisor(sl),
              MissionDriftDetector(drift_threshold=5.0), EvidenceProvenanceValidator()]:
        pipe.register_validator(v)
    return pipe


def run_endurance(cycles: int, mode: str = "fast", seed: int = 42,
                  out_json: str = "") -> dict:
    cp_dir = "/tmp/telos_endurance_cp"
    if os.path.isdir(cp_dir):
        shutil.rmtree(cp_dir)
    os.makedirs(cp_dir, exist_ok=True)
    load_start = read_load()
    pipe = build_pipeline(cp_dir, seed=seed, fast=(mode == "fast"))
    state = np.array([0.0, 0.0])

    # instrument the checkpointer so checkpoint mean latency is REAL
    ckpt_times = []
    _orig_save = pipe._checkpointer.save

    def timed_save(*a, **k):
        t0 = time.time()
        try:
            return _orig_save(*a, **k)
        finally:
            ckpt_times.append((time.time() - t0) * 1000.0)

    pipe._checkpointer.save = timed_save

    # instrumentation
    serializations = {"n": 0}
    _orig_td = DecisionTrace.to_dict

    def count_td(self, *a, **k):
        serializations["n"] += 1
        return _orig_td(self, *a, **k)

    DecisionTrace.to_dict = count_td
    axioms_md_reads = {"n": 0}
    real_open = open

    def count_open(*a, **k):
        p = str(a[0]) if a else ""
        if "AXIOMS.md" in p:
            axioms_md_reads["n"] += 1
        return real_open(*a, **k)

    import builtins
    builtins.open = count_open

    # Bounded instrumentation buffers — the harness must NOT retain one object
    # per cycle, or the memory gate would measure the HARNESS's own growth
    # rather than the pipeline's (that is exactly the leak class the gate
    # detects). di_min is a running scalar; the series keep only read windows.
    di_series = deque(maxlen=200)
    md_series = deque(maxlen=200)
    cycle_times = deque(maxlen=2000)
    di_min = 1.0
    firewall_blocks = {}     # blocked_by -> count
    trap_blocks = 0          # action_loop blocks (loop traps)
    escapes = 0              # goal_seek_recovery selections
    stagnation_arms = 0
    mem_samples = []          # {i, rss_kb, blocks} post-warmup samples
    cur_trap_streak = 0
    max_trap_streak = 0
    t0_run = time.time()

    try:
        for i in range(cycles):
            t0 = time.time()
            r = pipe.execute(state, user_name="endurance")
            cycle_times.append((time.time() - t0) * 1000.0)
            t = r.decision_trace
            di_val = float(t.decision_integrity or 0.0)
            di_series.append(di_val)
            if di_val < di_min:
                di_min = di_val
            md_series.append(float(t.mission_drift or 0.0))
            itype = t.selected_intent.intent_type if t.selected_intent else "none"
            if itype == "goal_seek_recovery":
                escapes += 1
            if t.firewall_blocked:
                bb = t.firewall_blocked_by or "unknown"
                firewall_blocks[bb] = firewall_blocks.get(bb, 0) + 1
                if bb == "action_loop":
                    trap_blocks += 1
                    cur_trap_streak += 1
                    max_trap_streak = max(max_trap_streak, cur_trap_streak)
                else:
                    cur_trap_streak = 0
            else:
                cur_trap_streak = 0
            if getattr(pipe, "_recovery_goal_seek_pending", False):
                stagnation_arms += 1
            act = t.selected_action
            if act is not None:
                nxt = pipe.config.simulator.transition(state, act)
                if 0.0 <= float(nxt[0]) <= 4.0 and 0.0 <= float(nxt[1]) <= 4.0:
                    state = nxt
            if (i % 200 == 0) and i >= 200:
                mem_samples.append({
                    "i": i,
                    "rss_kb": current_rss_kb(),
                    "blocks": sys.getallocatedblocks(),
                })
    finally:
        builtins.open = real_open
        DecisionTrace.to_dict = _orig_td
        pipe._checkpointer.save = _orig_save

    elapsed = time.time() - t0_run
    load_end = read_load()
    # The gate keys off the WORSE of the start/end samples: a run that began
    # quiet but ended contended (or vice versa) is still not a clean measure.
    load = load_start if load_start["load_per_cpu"] >= load_end["load_per_cpu"] \
        else load_end
    # Final own-process sample. Leak detection is on RETENTION (pymalloc blocks),
    # not a single RSS endpoint — see memory_leak_metrics().
    mem_samples.append({
        "i": cycles - 1,
        "rss_kb": current_rss_kb(),
        "blocks": sys.getallocatedblocks(),
    })
    mem = memory_leak_metrics(mem_samples, cycles)
    ckpt_dir_len = len([f for f in os.listdir(cp_dir)
                        if f.startswith("checkpoint_") and f.endswith(".json")])

    # checkpoint timing + hmac chain verification (sparse numbering). Sort by
    # CYCLE number, not lexicographic name (checkpoint_10000 must follow 9980).
    ckpt_files = sorted(
        [os.path.join(cp_dir, f) for f in os.listdir(cp_dir)
         if f.startswith("checkpoint_") and f.endswith(".json")],
        key=lambda p: int(os.path.basename(p)
                          .replace("checkpoint_", "").replace(".json", "")))
    chain_ok = True
    prev_content_hash = None
    for f in ckpt_files:
        try:
            with open(f) as fp:
                data = json.load(fp)
            if prev_content_hash is not None:
                if data.get("prev_checkpoint_hash") != prev_content_hash:
                    chain_ok = False
                    break
            content_hash = hashlib.sha256(
                json.dumps({k: v for k, v in data.items() if k != "hmac"},
                           default=str, sort_keys=True).encode()
            ).hexdigest()
            prev_content_hash = content_hash
        except Exception:
            chain_ok = False
            break

    # RNG scanner re-run
    sys.path.insert(0, PROJECT)
    from telos.tools.perf_profiler import _scan_global_rng
    rng_hits = _scan_global_rng()

    # determinism check: two fresh pipelines, same seed, fixed 150-cycle runs
    det_a = _fingerprint(150, seed)
    det_b = _fingerprint(150, seed)

    # KG retention
    kg = pipe._infra_manager.knowledge
    edge_types = {}
    for e in kg._edges.values():
        edge_types[e.edge_type] = edge_types.get(e.edge_type, 0) + 1
    adjacency_sym = all(
        e.dst in kg._adjacency.get(e.src, set()) and
        e.src in kg._adjacency.get(e.dst, set())
        for e in kg._edges.values())

    # telemetry ring
    tl = pipe._telemetry
    telemetry_ring = len(tl._cycle_metrics)

    # axiom state
    from telos.core.axioms.registry import AXIOMS
    n_axioms = len(AXIOMS)

    # DI final window (bounded buffers; di_min is a running scalar)
    tail = list(di_series)
    tail_mean_di = float(np.mean(tail)) if tail else 0.0
    cycle_times_list = list(cycle_times)

    results = {
        "cycles": cycles,
        "mode": mode,
        "elapsed_s": round(elapsed, 2),
        "load": load,
        "load_start": load_start,
        "load_end": load_end,
        "cycle_mean_ms": round(float(np.mean(cycle_times_list)), 3),
        "cycle_p95_ms": round(sorted(cycle_times_list)[int(0.95 * len(cycle_times_list))], 3),
        "cycle_max_ms": round(float(max(cycle_times_list)), 3),
        "di_tail_mean": round(float(tail_mean_di), 4),
        "di_min": round(float(di_min), 4),
        "di_end_last": round(float(di_series[-1]), 4),
        "md_tail_mean": round(float(np.mean(list(md_series))), 4),
        "rss_end_kb": mem["rss_end_kb"],
        "rss_idle_kb": mem["rss_idle_kb"],
        "rss_drift_frac": mem["rss_drift_frac"],
        "warm_blocks": mem["warm_blocks"],
        "end_blocks": mem["end_blocks"],
        "leak_blocks_per_cycle": mem["leak_blocks_per_cycle"],
        "alloc_growth_frac": mem["alloc_growth_frac"],
        "trace_serializations_per_cycle": round(serializations["n"] / cycles, 4),
        "axioms_md_reads": axioms_md_reads["n"],
        "axioms": n_axioms,
        "rng_global_hits": len(rng_hits),
        "determinism_ok": det_a == det_b,
        "determinism_fp": det_a[:16],
        "telemetry_ring_len": telemetry_ring,
        "kg_nodes": len(kg._nodes),
        "kg_edges": len(kg._edges),
        "kg_edge_types": edge_types,
        "kg_adjacency_symmetric": bool(adjacency_sym),
        "checkpoint_mean_ms": round(float(np.mean(ckpt_times)), 3) if ckpt_times else 0.0,
        "checkpoint_files": ckpt_dir_len,
        "checkpoint_chain_ok": bool(chain_ok),
        "firewall_blocks": firewall_blocks,
        "trap_blocks": trap_blocks,
        "escapes": escapes,
        "stagnation_arms": stagnation_arms,
        "trap_fraction": round(trap_blocks / max(cycles, 1), 5),
        "max_trap_streak": max_trap_streak,
    }
    return results


def _fingerprint(cycles: int, seed: int) -> str:
    cp = "/tmp/telos_endurance_det"
    try:
        import shutil
        if os.path.exists(cp):
            shutil.rmtree(cp)
        os.makedirs(cp, exist_ok=True)
        pipe = build_pipeline(cp, seed=seed, fast=True)
        state = np.array([0.0, 0.0])
        parts = []
        for _ in range(cycles):
            r = pipe.execute(state, user_name="det")
            t = r.decision_trace
            parts.append(
                f"{t.decision_integrity:.3f}:{t.mission_drift:.3f}:"
                f"{t.selected_intent.intent_type if t.selected_intent else 'none'}"
                f":{t.council_validated}")
            act = t.selected_action
            if act is not None:
                nxt = pipe.config.simulator.transition(state, act)
                if 0.0 <= float(nxt[0]) <= 4.0 and 0.0 <= float(nxt[1]) <= 4.0:
                    state = nxt
        return hashlib.sha256("|".join(parts).encode()).hexdigest()
    finally:
        import shutil
        if os.path.exists(cp):
            shutil.rmtree(cp)


def check(results: dict, ignore_load: bool = False,
          guard: dict = None) -> dict:
    """Evaluate each invariant against the stability contract.

    Returns {invariant: (status, measured, expected)} where status is one of
    "PASS", "FAIL", or "SKIPPED". Load-sensitive checks (memory_stability,
    checkpoint_latency) become "SKIPPED" -- never PASS, never FAIL -- when the
    host load signal exceeds the guard, because under contention those
    measurements describe the machine, not TELOS. A genuine regression still
    FAILs whenever the check actually runs.

    Args:
        results: the measured results dict from run_endurance().
        ignore_load: True (--force / --ignore-load) runs the load-sensitive
            checks regardless of host load, so a release gate can demand a
            real measurement.
        guard: optional threshold override (defaults to LOAD_GUARD).
    """
    g = guard or LOAD_GUARD
    load = results.get("load") or {}
    reason = "" if ignore_load else load_reason(load, g)
    out = {}
    out["di_stability"] = (results["di_tail_mean"] >= STABILITY["di_floor"], results["di_tail_mean"], f">={STABILITY['di_floor']}")
    leak_slope = results.get("leak_blocks_per_cycle", 0.0)
    rss_end = results.get("rss_end_kb", 0)
    mem_ok = (leak_slope <= STABILITY["leak_blocks_per_cycle"]
              and rss_end <= STABILITY["rss_ceiling_kb"])
    out["memory_stability"] = (
        mem_ok,
        (f"retained {leak_slope}/cyc "
         f"(warm {results.get('warm_blocks')}→end {results.get('end_blocks')} blocks), "
         f"RSS {rss_end/1024:.1f}MB"),
        (f"retained<={STABILITY['leak_blocks_per_cycle']}/cyc and "
         f"RSS<={STABILITY['rss_ceiling_kb']//1024}MB (one-sided)"),
    )
    out["rng_global"] = (results["rng_global_hits"] == 0, results["rng_global_hits"], "==0")
    out["determinism"] = (results["determinism_ok"], results["determinism_fp"], "same fingerprint twice")
    out["trace_retention"] = (results["telemetry_ring_len"] <= 200, results["telemetry_ring_len"], "<=200")
    out["kg_edges_capped"] = (results["kg_edges"] <= STABILITY["kg_edges_total_cap"], results["kg_edges"], f"<={STABILITY['kg_edges_total_cap']}")
    pt = max(results["kg_edge_types"].values(), default=0)
    out["kg_per_type_capped"] = (pt <= STABILITY["kg_edges_per_type_cap"], pt, f"<={STABILITY['kg_edges_per_type_cap']}")
    out["kg_adjacency_symmetric"] = (results["kg_adjacency_symmetric"], results["kg_adjacency_symmetric"], "True")
    out["checkpoint_latency"] = (results["checkpoint_mean_ms"] < STABILITY["checkpoint_mean_ms"], results["checkpoint_mean_ms"], f"<{STABILITY['checkpoint_mean_ms']}ms")
    out["checkpoint_retention"] = (results["checkpoint_files"] <= STABILITY["checkpoint_max_files"], results["checkpoint_files"], f"<={STABILITY['checkpoint_max_files']}")
    out["checkpoint_chain"] = (results["checkpoint_chain_ok"], results["checkpoint_chain_ok"], "True")
    out["axiom_integrity"] = (results["axioms"] == 42, results["axioms"], "==42")
    out["axiom_no_reparse"] = (results["axioms_md_reads"] == 0, results["axioms_md_reads"], "==0")
    out["firewall_no_infinite_trap"] = (
        results["max_trap_streak"] <= STABILITY["max_trap_streak"],
        results["max_trap_streak"],
        f"streak<={STABILITY['max_trap_streak']}",
    )
    # Normalise every entry to the three-state string contract
    # ("PASS"/"FAIL"/"SKIPPED") so no consumer treats a skip as a bool pass.
    out = {n: (("PASS" if v[0] else "FAIL"), v[1], v[2])
           for n, v in out.items()}
    if reason:
        for name in LOAD_SENSITIVE_CHECKS:
            _, measured, expected = out[name]
            out[name] = ("SKIPPED", measured,
                         f"load guard: {reason} (expected {expected})")
    return out


def verdict_exit_code(overall: str, strict: bool = False) -> int:
    """Map the three-state verdict to a process exit code.

    PASS -> 0. Any FAIL -> 1 (a real regression must block). INCOMPLETE (a
    load-sensitive check was SKIPPED, no failures) -> 0 by default: it is
    honestly *not* a pass, so it is reported as INCOMPLETE rather than PASS,
    but a contended local run should not look like a failure. --strict maps
    INCOMPLETE -> 2 so a release pipeline can refuse an unmeasured check.

    Args:
        overall: "PASS", "FAIL", or "INCOMPLETE".
        strict: treat a skip as a non-zero (2) result.
    """
    if overall == "FAIL":
        return 1
    if overall == "INCOMPLETE":
        return 2 if strict else 0
    return 0


def print_table(results: dict, checks: dict) -> str:
    """Print the three-state report. Returns "PASS", "FAIL", or "INCOMPLETE"."""
    print("\n" + "=" * 84)
    print(f"TELOS v7 STABILITY GATE — {results['cycles']:,} cycles ({results['mode']})")
    print("=" * 84)
    print(f"{'metric':<30}{'measured':>16}{'expected':>18}{'':>10}")
    print("-" * 84)
    rows = [
        ("elapsed", f"{results['elapsed_s']}s", "run to completion"),
        ("cycle mean", f"{results['cycle_mean_ms']}ms", "<100ms"),
        ("cycle p95", f"{results['cycle_p95_ms']}ms", "<150ms"),
        ("DI tail mean", f"{results['di_tail_mean']}", f">={STABILITY['di_floor']}"),
        ("DI min", f"{results['di_min']}", "no frozen plateau"),
        ("RSS end (own)", f"{results['rss_end_kb']/1024:.1f}MB", f"<={STABILITY['rss_ceiling_kb']//1024}MB"),
        ("retained slope", f"{results.get('leak_blocks_per_cycle')}/cyc", f"<={STABILITY['leak_blocks_per_cycle']}"),
        ("RSS drift (info)", f"{results['rss_drift_frac']:.1%}", "reported only"),
        ("trace serial/cycle", f"{results['trace_serializations_per_cycle']}", "<=1"),
        ("rng global hits", f"{results['rng_global_hits']}", "==0"),
        ("determinism fp", results["determinism_fp"][:16], "twice identical"),
        ("telemetry ring", f"{results['telemetry_ring_len']}", "<=200"),
        ("KG nodes/edges", f"{results['kg_nodes']}/{results['kg_edges']}", "caps hold"),
        ("KG adj symmetric", f"{results['kg_adjacency_symmetric']}", "True"),
        ("checkpoint mean", f"{results['checkpoint_mean_ms']}ms", "<100ms"),
        ("checkpoint files", f"{results['checkpoint_files']}", "<=10"),
        ("checkpoint chain", f"{results['checkpoint_chain_ok']}", "True"),
        ("axioms", f"{results['axioms']}", "==42"),
        ("axiom re-reads", f"{results['axioms_md_reads']}", "==0"),
        ("max trap streak", f"{results['max_trap_streak']}", f"<={STABILITY['max_trap_streak']}"),
        ("escapes (designed)", f"{results['escapes']}", ">0 when needed"),
    ]
    for name, m, e in rows:
        print(f"{name:<30}{m:>16}{e:>18}")
    print("-" * 84)
    statuses = [c[0] for c in checks.values()]
    any_fail = "FAIL" in statuses
    skipped = [(n, c) for n, c in checks.items() if c[0] == "SKIPPED"]
    print("INVARIANTS (three-state):")
    for name, (status, m, e) in checks.items():
        print(f"  [{status}] {name:<32} measured={m} expected {e}")
    overall = "FAIL" if any_fail else ("INCOMPLETE" if skipped else "PASS")
    if skipped:
        load = results.get("load") or {}
        print("-" * 84)
        print(f"SKIPPED under load (not counted as PASS) — "
              f"load1/cpu={load.get('load_per_cpu')}, "
              f"swap={load.get('swap_frac')}, "
              f"heavy_procs={load.get('heavy_procs')}:")
        for name, (_, m, e) in skipped:
            print(f"  - {name}: {e}")
    print("=" * 84)
    print("STABILITY GATE:", overall)
    return overall


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="v7 stability-gate endurance run")
    ap.add_argument("--cycles", type=int, default=10000)
    ap.add_argument("--mode", choices=["fast", "standard"], default="fast")
    ap.add_argument("--json", default="")
    ap.add_argument("--force", "--ignore-load", dest="ignore_load",
                    action="store_true",
                    default=os.environ.get("TELOS_ENDURANCE_IGNORE_LOAD") == "1",
                    help="run load-sensitive checks regardless of host load "
                         "(release/CI mode on a quiet machine)")
    ap.add_argument("--strict", action="store_true",
                    help="treat SKIPPED checks as a non-zero (exit 2) result")
    ap.add_argument("--max-load-per-cpu", type=float,
                    default=float(os.environ.get(
                        "TELOS_ENDURANCE_MAX_LOAD_PER_CPU",
                        LOAD_GUARD["max_load_per_cpu"])),
                    help="1-min loadavg / cpu_count skip threshold")
    ap.add_argument("--max-swap-frac", type=float,
                    default=float(os.environ.get(
                        "TELOS_ENDURANCE_MAX_SWAP_FRAC",
                        LOAD_GUARD["max_swap_frac"])),
                    help="swap-used fraction skip threshold")
    args = ap.parse_args()
    guard = {"max_load_per_cpu": args.max_load_per_cpu,
             "max_swap_frac": args.max_swap_frac}
    res = run_endurance(cycles=args.cycles, mode=args.mode)
    checks = check(res, ignore_load=args.ignore_load, guard=guard)
    overall = print_table(res, checks)
    if args.json:
        with open(args.json, "w") as f:
            json.dump({**res, "invariants": {k: v[0] for k, v in checks.items()},
                       "overall": overall}, f, indent=2)
        print(f"(results saved: {args.json})")
    # Exit codes: PASS=0; any FAIL=1; INCOMPLETE (skips, no fail) = 0 by
    # default (honest: it is not a PASS), or 2 under --strict for pipelines
    # that must never silently accept an unmeasured load-sensitive check.
    sys.exit(verdict_exit_code(overall, strict=args.strict))
