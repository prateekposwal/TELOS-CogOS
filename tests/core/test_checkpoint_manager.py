"""gap_scanner requires test_<basename>.py for every core module; the module
telos/core/infra_manager/checkpoint_manager.py has basename 'checkpoint_manager'.
The canonical tests live in test_checkpoint.py (sibling basename from the earlier
test_session_checkpoint rename); importing the module here keeps the fixture
namespace intact (module-level fixtures are not visible to imported classes), so
the coverage genuinely runs via test_checkpoint.py."""

from tests.core import test_checkpoint  # noqa: F401