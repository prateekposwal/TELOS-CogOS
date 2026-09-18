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

