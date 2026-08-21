"""
RepoEvidenceValidator — the council GENUINELY READS raw repo artifacts.

PATTERN UNDER TEST (real perception): raw artifacts reach the council as
evidence, never hidden behind a vector. These tests build synthetic-but-raw
RepoSnapshot dicts (as produced by GitRepoSim.gather_snapshot for REAL
repos) and assert the validator's reasons QUOTE the raw failing-test names
and traceback lines — the council's dissent names the actual artifact.
"""

import numpy as np
import pytest

from telos.core.council.validators.repo_evidence import (
    RepoEvidenceValidator, TRACEBACK_QUOTE,
)
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.intent_ir import IntentIR


def snapshot_facts(repo_snapshot_dict, state=None):
    """Build DomainFacts carrying a repo_snapshot evidence channel.

    Args:
        repo_snapshot_dict: the RepoSnapshot.to_dict() payload.
        state: numeric vector (defaults to a 7-dim zeros vector).

    Returns:
        DomainFacts with metadata.repo_snapshot set.
    """
    vec = np.zeros(7) if state is None else np.asarray(state, dtype=float)
    return DomainFacts(
        state=vec,
        resources={}, constraints=[], events=[],
        metrics={},
        metadata={"repo_snapshot": repo_snapshot_dict, "repo_path": "/tmp/r"},
    )


class TestRepoEvidenceValidator:
    """Validator behavior on raw snapshot evidence."""

    def test_dissent_quotes_real_failing_test_names(self):
        snap = {
            "repo_path": "/tmp/r",
            "changed_files": [
                {"path": "app/calculator.py", "status": "M", "added": 1, "removed": 1},
                {"path": "tests/test_calculator.py", "status": "M", "added": 2, "removed": 0},
            ],
            "failing_test_names": ["tests/test_calculator.py::test_add"],
            "traceback_frames": [],
            "diff_text": "@@ -1,2 +1,2 @@\n-    return a + b\n+    return a - b\n",
            "added_lines": 3, "removed_lines": 1,
            "findings": ["test failure: 1 failing in out.txt"],
            "evidence_provenance": {"git_status": "measured",
                                    "test_output": "measured"},
        }
        signal = RepoEvidenceValidator().validate(
            World(state=np.zeros(7)), IntentIR("fix_bug"), snapshot_facts(snap))
        assert signal.passed is False
        # The dissent cites the RAW failing-test id, not a numeric abstraction.
        assert "tests/test_calculator.py::test_add" in signal.reason
        assert signal.metadata["failing_tests"] == \
            ["tests/test_calculator.py::test_add"]

    def test_dissent_quotes_traceback_frame_naming_changed_file(self):
        snap = {
            "changed_files": [{"path": "src/loader.py", "status": "M",
                               "added": 1, "removed": 0}],
            "failing_test_names": [],
            "traceback_frames": [
                '  File "/x/tests/test_loader.py", line 3, in test_loader',
                "ModuleNotFoundError: No module named 'src.loader'",
            ],
            "diff_text": "", "added_lines": 1, "removed_lines": 0,
            "findings": [], "evidence_provenance": {"test_output": "measured"},
        }
        signal = RepoEvidenceValidator().validate(
            World(state=np.zeros(7)), None, snapshot_facts(snap))
        assert signal.passed is False
        assert "traceback frame" in signal.reason
        assert "src/loader.py" in signal.reason

    def test_abstain_when_no_repo_snapshot(self):
        facts = DomainFacts(
            state=np.zeros(2), resources={}, constraints=[],
            events=[], metrics={}, metadata={"domain": "gridworld"},
        )
        signal = RepoEvidenceValidator().validate(
            World(state=np.zeros(2)), None, facts)
        assert signal.passed is True
        assert signal.evidence_weight == 0.0
        assert "no repo snapshot" in signal.reason

    def test_clean_measured_repo_passes_with_confidence(self):
        snap = {
            "changed_files": [{"path": "README.md", "status": "M",
                               "added": 1, "removed": 1}],
            "failing_test_names": [],
            "traceback_frames": [],
            "diff_text": "- old\n+ new\n",
            "added_lines": 1, "removed_lines": 1,
            "findings": ["working tree dirty: 1 changed file"],
            "evidence_provenance": {"git_status": "measured",
                                    "git_diff": "measured",
                                    "test_output": "measured"},
        }
        signal = RepoEvidenceValidator().validate(
            World(state=np.zeros(7)), None, snapshot_facts(snap))
        assert signal.passed is True
        assert signal.confidence > 0.5  # measured clean evidence earns confidence
        assert "0 failing tests" in signal.reason

    def test_large_diff_without_test_evidence_is_advisory_not_block(self):
        snap = {
            "changed_files": [],
            "failing_test_names": [],
            "traceback_frames": [],
            "diff_text": "x", "added_lines": 900, "removed_lines": 0,
            "findings": ["diff magnitude: +900/-0 lines"],
            "evidence_provenance": {"git_status": "measured"},
        }
        signal = RepoEvidenceValidator().validate(
            World(state=np.zeros(7)), IntentIR("big_refactor"), snapshot_facts(snap))
        assert signal.passed is True  # advisory only — no safety violation
        assert "NO test evidence measured" in signal.reason
        assert "advisory" in signal.reason

    def test_unmeasured_repo_passes_with_low_confidence(self):
        snap = {
            "changed_files": [], "failing_test_names": [],
            "traceback_frames": [], "diff_text": "",
            "added_lines": 0, "removed_lines": 0,
            "findings": [], "evidence_provenance": {},
        }
        signal = RepoEvidenceValidator().validate(
            World(state=np.zeros(7)), None, snapshot_facts(snap))
        assert signal.passed is True
        assert signal.confidence < 0.5  # nothing measured => modest confidence

    def test_module_exports(self):
        assert TRACEBACK_QUOTE >= 1
        assert RepoEvidenceValidator().name == "RepoEvidenceValidator"
