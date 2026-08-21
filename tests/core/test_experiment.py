"""gap_scanner requires test_<basename>.py for every core module; the module
telos/core/reasoning/theory/experiment.py has basename 'experiment', so this
file exists as a redirect to the canonical theory-experiment tests in
test_theory_experiment.py."""

from tests.core.test_theory_experiment import (  # noqa: F401
    TestExperimentOutcome,
    TestExperimentDefaults,
    TestRunExperimentConfirmed,
    TestRunExperimentFalsified,
    TestRunExperimentInconclusive,
    TestExperimentRecord,
)