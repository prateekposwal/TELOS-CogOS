"""
Version lock — pyproject.toml and telos.__version__ must agree.

A release bump that touches only one site would ship a package whose metadata
disagrees with the code. This test makes that impossible.
"""

import os
import re

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _pyproject_version() -> str:
    """Read [project] version from pyproject.toml.

    Returns:
        The declared version string.

    Raises:
        AssertionError: when no version is declared.
    """
    path = os.path.join(PROJECT, "pyproject.toml")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    assert match is not None, "pyproject.toml declares no [project] version"
    return match.group(1)


def test_version_sites_agree():
    """telos.__version__ equals the pyproject version."""
    import telos
    assert telos.__version__ == _pyproject_version()


def test_version_is_semver():
    """The version is MAJOR.MINOR.PATCH."""
    import telos
    assert re.match(r"^\d+\.\d+\.\d+$", telos.__version__), telos.__version__


def test_version_exposed_on_package():
    """The version is part of the public package surface."""
    import telos
    assert "__version__" in telos.__all__


def test_changelog_mentions_current_version():
    """The changelog documents the current version (no silent bump)."""
    import telos
    path = os.path.join(PROJECT, "CHANGELOG.md")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert telos.__version__ in content, \
        f"CHANGELOG.md has no entry for {telos.__version__}"
