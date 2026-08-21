"""gap_scanner requires test_<basename>.py for every core module; the module
telos/core/perception/gate.py has basename 'gate', so this file exists as a
redirect to the canonical ResolutionGate tests in test_perception_gate.py."""

from tests.core.test_perception_gate import (  # noqa: F401
    TestEvaluate,
    TestGateVerdict,
    TestThreshold,
)