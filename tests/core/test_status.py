"""gap_scanner requires test_<basename>.py for every core module; the module
telos/core/ui/status.py has basename 'status', so this file exists as a
redirect to the canonical UI-status tests in test_ui_status.py."""

from tests.core.test_ui_status import (  # noqa: F401
    test_phases_are_canonical,
    test_disabled_display_renders_nothing,
    test_enabled_display_renders_cycle,
    test_freeze_writes_and_flags,
    test_phase_emoji_map_covers_labels,
)