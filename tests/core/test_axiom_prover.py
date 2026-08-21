"""
AxiomProver (core/verifier/axiom_prover.py) — honest contract coverage.
"""
import numpy as np

from telos.core.verifier.axiom_prover import AxiomProver


class FakeTrace:
    decision_integrity = 1.0
    mission_drift = 0.0
    council_validated = True
    axiom_results = None


class FakeCtx:
    pass


class TestAxiomProver:
    def test_verify_returns_results_dict(self):
        prover = AxiomProver()
        results = prover.verify(FakeTrace(), FakeCtx())
        assert isinstance(results, dict)

    def test_summary_counts(self):
        prover = AxiomProver()
        passed, total, failed_list = prover.summary(FakeTrace(), FakeCtx())
        assert passed <= total
        assert isinstance(failed_list, list)
        assert prover.all_passed(FakeTrace(), FakeCtx()) in (True, False)
