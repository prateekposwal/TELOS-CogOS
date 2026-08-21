"""gap_scanner requires test_<basename>.py for every core module; the module
telos/core/perception/quality.py has basename 'quality', so this file exists as
a redirect to the canonical PerceptionQuality tests in test_perception_quality.py."""

from tests.core.test_perception_quality import (  # noqa: F401
    TestAssess,
    TestQualityReport,
)