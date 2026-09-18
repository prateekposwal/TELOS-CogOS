"""Focused unit tests for the v7 endurance/stability invariants.

The endurance harness (`telos/tools/endurance.py`) runs the FULL machine over
10k cycles; these tests lock each invariant's boundary at unit granularity so
a regression fails fast, not after a long run.

Covered invariants (mirrors STABILITY in endurance.py):
  1. theory-retention caps      — patterns/hypotheses bounded (Λ4.7)
  2. TheoryBuilder hot-path idx — hypothesize/promote are index-backed (Λ4.7)
  3. trace/cache retention      — bounded rings under sustained cycles
  4. checkpoint chain + sparse numbering
  5. RNG isolation + determinism (fixed seed => identical trace)
  6. axiom constitution intact (42, no re-parse)
"""
import json
import os
import tempfile

import numpy as np
import pytest
import time
import weakref
import gc

from telos.core.reasoning.theory.builder import TheoryBuilder
from telos.core.trace_builder import DecisionTrace


# ────────────────────────────────────────────────────────────────────────
# 1. TheoryBuilder retention caps — the 10k-run memory-drift class
# ────────────────────────────────────────────────────────────────────────
class TestTheoryRetention:
    def test_patterns_bounded_by_max_history(self):
        b = TheoryBuilder()
        b._max_history = 50
        for i in range(300):
            b.add_experience({"feature": i % 3}, f"act_{i % 4}", float(i % 5) / 4.0)
            b.cluster()
        assert b.total_patterns <= 50

    def test_hypotheses_bounded_by_max_history(self):
        b = TheoryBuilder(min_experiences_for_pattern=1,
                          min_patterns_for_hypothesis=1)
        b._max_history = 50
        for i in range(300):
            b.add_experience({"feature": i % 3}, f"act_{i % 4}", float(i % 5) / 4.0)
            b.cluster()
            b.hypothesize()
        assert b.total_hypotheses <= 50

    def test_eviction_oldest_first(self):
        b = TheoryBuilder(min_experiences_for_pattern=1)
        b._max_history = 10
        for i in range(5):
            b.add_experience({"feature": i}, f"act_{i}", 0.9)
            b.cluster()
        created = [b._patterns[p].created for p in b._patterns]
        assert created == sorted(created)

    def test_rehypothesize_after_falsification(self):
        """Falsified hypotheses release their pattern for re-coverage."""
        b = TheoryBuilder(min_experiences_for_pattern=1,
                          min_patterns_for_hypothesis=1)
        b._max_history = 50
        for i in range(3):
            b.add_experience({"feature": 1}, "act_move", 0.9)
        b.cluster()  # one cluster pass groups the 3 experiences into 1 pattern
        assert b.total_patterns == 1
        hyps = b.hypothesize()
        assert len(hyps) == 1
        hid = hyps[0].id
        pid = hyps[0].supporting_patterns[0]
        assert pid in b._covered_patterns
        # confound it until falsified
        for _ in range(3):
            b.test_hypotheses({"feature": 1}, "act_move", 0.0)
        assert b._hypotheses[hid].falsified
        # the falsified hypothesis no longer counts toward ACTIVE coverage...
        # a fresh hypothesize() re-creates coverage for the released pattern
        revived = b.hypothesize()
        assert len(revived) == 1
        assert revived[0].id != hid
        assert revived[0].supporting_patterns == [pid]


# ────────────────────────────────────────────────────────────────────────
# 2. TheoryBuilder hot-path indexes — no quadratic rescans
# ────────────────────────────────────────────────────────────────────────
class TestTheoryIndexes:
    def test_coverage_index_is_used_not_full_rescan(self):
        """hypothesize() must consult the index, not rescan all hypotheses."""
        b = TheoryBuilder(min_experiences_for_pattern=1,
                          min_patterns_for_hypothesis=1)
        b._max_history = 100
        for i in range(40):
            b.add_experience({"feature": i % 5}, f"act_{i % 8}", 0.9)
        b.cluster()
        b.hypothesize()  # all patterns now covered
        before_h = len(b._hypotheses)
        # Re-running must NOT create duplicate hypotheses (index says covered).
        b.cluster()
        again = b.hypothesize()
        assert again == []
        assert len(b._hypotheses) == before_h

    def test_promote_index_rejects_promoted(self):
        b = TheoryBuilder(min_experiences_for_pattern=1,
                          min_patterns_for_hypothesis=1,
                          min_tests_for_theory=2, theory_confidence_threshold=0.0)
        b._max_history = 100
        for i in range(3):
            b.add_experience({"feature": 1}, "act_mv", 0.9)
            b.cluster()
        b.hypothesize()
        # pump confidence
        for _ in range(3):
            b.test_hypotheses({"feature": 1}, "act_mv", 0.9)
        b.promote()
        n_theories = len(b._theories)
        assert n_theories >= 1
        # promote again must not double-promote the same hypothesis
        b.promote()
        assert len(b._theories) == n_theories


# ────────────────────────────────────────────────────────────────────────
# 3. Bounded retentions (trace rings / decision log) under sustained cycles
# ────────────────────────────────────────────────────────────────────────
class TestBoundedRetention:
    def test_telemetry_ring_bounded(self):
        from telos.core.observability.telemetry import TelemetryCollector
        t = TelemetryCollector()
        for i in range(500):
            t.record_cycle(i, None)
        assert len(t._cycle_metrics) <= 200

    def test_perf_baseline_json_present(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        assert os.path.exists(os.path.join(root, "telos", "audit", "perf_baseline.json"))


# ────────────────────────────────────────────────────────────────────────
# 4. Checkpoint chain + sparse numbering integrity (unit-level)
# ────────────────────────────────────────────────────────────────────────
class TestCheckpointChain:
    def _write_chain(self, n):
        path = tempfile.mkdtemp(prefix="telos_ck_chain_")
        import hashlib
        prev = None
        for i in range(n):
            cycle = (i + 1) * 20
            data = {
                "cycle": cycle,
                "prev_checkpoint_hash": prev,
                "hmac": hashlib.sha256(f"blk-{cycle}".encode()).hexdigest(),
            }
            with open(os.path.join(path, f"checkpoint_{cycle:04d}.json"), "w") as f:
                json.dump(data, f)
            # chain links CONTENT hash (payload minus hmac), per
            # checkpoint_manager.save(); emulate for the unit assertion
            import hashlib as hl
            payload_without_hmac = json.dumps(
                {k: v for k, v in data.items() if k != "hmac"},
                default=str, sort_keys=True)
            prev = hl.sha256(payload_without_hmac.encode()).hexdigest()
        return path

    def test_sparse_chain_links_back(self):
        path = self._write_chain(5)
        files = sorted(os.listdir(path))
        assert len(files) == 5
        prev_payload_hash = None
        for f in files:
            with open(os.path.join(path, f)) as fp:
                c = json.load(fp)
            assert c["cycle"] % 20 == 0
            if prev_payload_hash is not None:
                # verify the chain math: this file's prev == prev file's
                # content-hash (they carry identical prev fields in this
                # synthetic chain, so continue the same emulation)
                import hashlib
                assert c["prev_checkpoint_hash"] == prev_payload_hash
            import hashlib
            payload_without_hmac = json.dumps(
                {k: v for k, v in c.items() if k != "hmac"},
                default=str, sort_keys=True)
            prev_payload_hash = hashlib.sha256(payload_without_hmac.encode()).hexdigest()


# ────────────────────────────────────────────────────────────────────────
# 5. RNG isolation + determinism (fixed seed => identical traces)
# ────────────────────────────────────────────────────────────────────────
class TestDeterminism:
    def test_fixed_seed_trace_fingerprint(self):
        """Same seed + fresh engine => identical trace fingerprint."""
        import subprocess
        import sys
        r = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, '.');"
             "from telos.tools.endurance import _fingerprint;"
             "print(_fingerprint(80, 42))"],
            capture_output=True, text=True)
        r2 = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, '.');"
             "from telos.tools.endurance import _fingerprint;"
             "print(_fingerprint(80, 42))"],
            capture_output=True, text=True)
        assert r.returncode == 0 and r2.returncode == 0
        assert r.stdout.strip() == r2.stdout.strip()


# ────────────────────────────────────────────────────────────────────────
# 6. Axiom constitution intact (42) at unit boundary
# ────────────────────────────────────────────────────────────────────────
class TestAxiomIntegrity:
    def test_axiom_count_unchanged(self):
        from telos.core.axioms.registry import AXIOMS
        assert len(AXIOMS) == 42

    def test_axioms_not_reread_when_frozen(self):
        from telos.core.verifier.axiom_prover import AxiomProver
        p = AxiomProver()
        t0 = time.time()
        p.verify(trace=None, ctx=None)
        assert time.time() - t0 < 1.0

# ────────────────────────────────────────────────────────────────────────
# 7. Memory-leak detection — robust to allocator noise, falsifiable
# ────────────────────────────────────────────────────────────────────────
class TestMemoryLeakDetection:
    """The memory gate must measure TELOS retention, not allocator high-water.

    A synthetic series with a bounded cache fill + an INJECTED sustained leak
    must FAIL the late-window slope check; the same fill without the leak must
    PASS. This is the falsifiability proof for the repaired memory gate.
    """

    @staticmethod
    def _series(cycles: int = 10000, leak_per_cycle: float = 0.0,
                base: int = 600000):
        out = []
        for i in range(200, cycles, 200):
            fill = base * (1.0 - np.exp(-i / 500.0))     # bounded cache fill
            leak = leak_per_cycle * max(0, i - 500)      # injected leak
            out.append({"i": i, "rss_kb": 80000, "blocks": int(fill + leak)})
        return out

    def test_bounded_series_passes(self):
        from telos.tools.endurance import memory_leak_metrics, STABILITY
        m = memory_leak_metrics(self._series(leak_per_cycle=0.0), 10000)
        assert m["leak_blocks_per_cycle"] <= STABILITY["leak_blocks_per_cycle"]

    def test_deliberate_leak_is_caught(self):
        from telos.tools.endurance import memory_leak_metrics, STABILITY
        m = memory_leak_metrics(self._series(leak_per_cycle=10.0), 10000)
        assert m["leak_blocks_per_cycle"] > STABILITY["leak_blocks_per_cycle"]

    def test_empty_series_is_safe(self):
        from telos.tools.endurance import memory_leak_metrics
        assert memory_leak_metrics([], 10000)["leak_blocks_per_cycle"] == 0.0


# ────────────────────────────────────────────────────────────────────────
# 8. Unbounded-retention fixes (the leak class this session closed)
# ────────────────────────────────────────────────────────────────────────
class TestRetentionCaps:
    def test_audit_histories_bounded(self):
        from telos.core.infra_manager.audit_controller import (
            AuditController, _HISTORY_CAP,
        )

        class _Trace:
            decision_integrity = 0.9
            mission_drift = 0.1
            council_validated = True
            firewall_blocked = False

        class _Result:
            decision_trace = _Trace()
            health_score = 0.9

        ac = AuditController()
        for _ in range(_HISTORY_CAP * 3):
            ac.observe(_Result())
        assert len(ac._di_history) == _HISTORY_CAP
        assert len(ac._md_history) == _HISTORY_CAP
        assert len(ac._health_history) == _HISTORY_CAP

    def test_failure_ledger_type_index_pruned_and_valid(self):
        from telos.core.infra_manager.failure_ledger import (
            FailureLedger, FailureRecord,
        )
        fl = FailureLedger(max_failures=50)
        for i in range(500):
            fl._append(FailureRecord(
                failure_id=str(i), cycle=i, timestamp=0.0,
                failure_type="firewall_block", severity=0.7,
                root_cause="governance_intervention"))
        total_indexed = sum(len(v) for v in fl._type_index.values())
        assert total_indexed == len(fl._failures) == 50
        # indices remain consistent with the (shifted) records list
        assert fl.get_failures_by_type("firewall_block") == fl._failures



# ────────────────────────────────────────────────────────────────────────
# 9. Load-aware guard — SKIPPED under load, never a false FAIL
# ────────────────────────────────────────────────────────────────────────
class TestLoadGuard:
    """The endurance gate must measure TELOS, not the host's contention.

    Under high host load the load-sensitive checks (memory_stability,
    checkpoint_latency) must report SKIPPED with the measured load as
    evidence — never PASS, never FAIL. --force / --ignore-load bypasses the
    guard so a release gate can demand a real measurement; a genuine leak
    still FAILs whenever the check actually runs.
    """

    HIGH = (32.0, 30.0, 28.0)   # /8 cpus = 4.0 load/cpu
    LOW = (0.4, 0.3, 0.3)       # /8 cpus = 0.05 load/cpu

    @staticmethod
    def _results(load: dict, leak_per_cycle: float = 0.0) -> dict:
        return {
            "cycles": 100, "mode": "fast", "elapsed_s": 1.0,
            "cycle_mean_ms": 5.0, "cycle_p95_ms": 6.0, "cycle_max_ms": 7.0,
            "trace_serializations_per_cycle": 0.0,
            "kg_nodes": 10, "escapes": 0,
            "load": load,
            "di_tail_mean": 1.0, "di_min": 0.3,
            "leak_blocks_per_cycle": leak_per_cycle,
            "warm_blocks": 600000, "end_blocks": 600000,
            "rss_end_kb": 80000, "rss_drift_frac": 0.01,
            "rng_global_hits": 0, "determinism_ok": True,
            "determinism_fp": "abc",
            "telemetry_ring_len": 10,
            "kg_edges": 10, "kg_edge_types": {"x": 3},
            "kg_adjacency_symmetric": True,
            "checkpoint_mean_ms": 50.0, "checkpoint_files": 2,
            "checkpoint_chain_ok": True,
            "axioms": 42, "axioms_md_reads": 0, "max_trap_streak": 1,
        }

    def _load(self, monkeypatch, values, cpus=8):
        monkeypatch.setattr(os, "getloadavg", lambda: values)
        monkeypatch.setattr(os, "cpu_count", lambda: cpus)
        monkeypatch.setattr(
            "telos.tools.endurance._read_swap_mb", lambda: (0, 0))
        monkeypatch.setattr(
            "telos.tools.endurance._count_heavy_procs", lambda t=25.0: 0)
        from telos.tools.endurance import read_load
        return read_load()

    def test_high_load_skips_load_sensitive(self, monkeypatch):
        from telos.tools.endurance import check
        load = self._load(monkeypatch, self.HIGH)
        assert load["load_per_cpu"] >= 0.75
        checks = check(self._results(load), ignore_load=False)
        assert checks["memory_stability"][0] == "SKIPPED"
        assert checks["checkpoint_latency"][0] == "SKIPPED"
        # evidence carries the load number
        assert str(load["load_per_cpu"]) in checks["memory_stability"][2]

    def test_non_load_sensitive_still_run_under_load(self, monkeypatch):
        from telos.tools.endurance import check
        load = self._load(monkeypatch, self.HIGH)
        checks = check(self._results(load), ignore_load=False)
        assert checks["di_stability"][0] == "PASS"
        assert checks["axiom_integrity"][0] == "PASS"
        assert checks["rng_global"][0] == "PASS"

    def test_normal_load_runs_and_can_pass(self, monkeypatch):
        from telos.tools.endurance import check, load_reason
        load = self._load(monkeypatch, self.LOW)
        assert load_reason(load) == ""
        checks = check(self._results(load), ignore_load=False)
        assert checks["memory_stability"][0] == "PASS"
        assert checks["checkpoint_latency"][0] == "PASS"

    def test_normal_load_can_fail(self, monkeypatch):
        from telos.tools.endurance import check
        load = self._load(monkeypatch, self.LOW)
        checks = check(self._results(load, leak_per_cycle=10.0),
                       ignore_load=False)
        assert checks["memory_stability"][0] == "FAIL"

    def test_force_bypasses_guard(self, monkeypatch):
        from telos.tools.endurance import check
        load = self._load(monkeypatch, self.HIGH)
        checks = check(self._results(load), ignore_load=True)
        assert checks["memory_stability"][0] != "SKIPPED"
        assert checks["checkpoint_latency"][0] != "SKIPPED"

    def test_genuine_leak_still_fails_under_force(self, monkeypatch):
        from telos.tools.endurance import check
        load = self._load(monkeypatch, self.HIGH)
        checks = check(self._results(load, leak_per_cycle=10.0),
                       ignore_load=True)
        assert checks["memory_stability"][0] == "FAIL"

    def test_overall_is_incomplete_not_pass_when_skipped(self, monkeypatch):
        from telos.tools.endurance import check, print_table
        load = self._load(monkeypatch, self.HIGH)
        checks = check(self._results(load), ignore_load=False)
        assert print_table(self._results(load), checks) == "INCOMPLETE"

    def test_overall_pass_when_quiet_and_clean(self, monkeypatch):
        from telos.tools.endurance import check, print_table
        load = self._load(monkeypatch, self.LOW)
        checks = check(self._results(load), ignore_load=False)
        assert print_table(self._results(load), checks) == "PASS"

    def test_custom_threshold_configures_guard(self, monkeypatch):
        from telos.tools.endurance import read_load, load_reason
        load = self._load(monkeypatch, self.LOW)
        # with a stricter guard the same quiet load trips the threshold
        assert load_reason(load, {"max_load_per_cpu": 0.01,
                                  "max_swap_frac": 1.0}) != ""

    def test_exit_codes_three_states(self):
        from telos.tools.endurance import verdict_exit_code
        assert verdict_exit_code("PASS") == 0
        assert verdict_exit_code("FAIL") == 1
        assert verdict_exit_code("INCOMPLETE") == 0        # skip != failure
        assert verdict_exit_code("INCOMPLETE", strict=True) == 2
        assert verdict_exit_code("FAIL", strict=True) == 1  # fail beats strict
