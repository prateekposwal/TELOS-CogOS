"""gap_scanner requires test_<basename>.py for every core module; the module
telos/core/phases/base.py has basename 'base', so this file exists as a
redirect to the canonical phase-base tests in test_phase_base.py."""

from tests.core.test_phase_base import (  # noqa: F401
    TestDataclasses,
    TestPhaseABC,
    TestPhaseContext,
)