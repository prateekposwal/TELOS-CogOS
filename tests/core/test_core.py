"""gap_scanner requires test_<basename>.py for every core module; the module
telos/core/pattern/core.py has basename 'core', so this file exists as a
redirect to the canonical pattern tests in test_pattern.py."""

from tests.core.test_pattern import (  # noqa: F401
    TestPatternSignature,
    TestRecordAndQuery,
    TestPatternMetadata,
    TestEviction,
    TestPersistence,
)