"""
Safe-write guard — never clobber a repository path without inspecting it.

The engineering invariant (from the V7 process note): before creating or
overwriting any path, resolve it, check existence, and distinguish
CREATE / MODIFY / REPLACE — with REPLACE requiring explicit justification.

This is a tiny guard, NOT a file-governance subsystem.
"""

from __future__ import annotations

import os
from typing import Callable


def classify(path: str) -> str:
    """Classify a write against an existing path.

    Args:
        path: the target path.

    Returns:
        "CREATE" when nothing exists there, else "REPLACE".
    """
    return "CREATE" if not os.path.exists(path) else "REPLACE"


def safe_create(path: str, content: str, *, encoding: str = "utf-8") -> str:
    """Create a NEW file; refuse if the path already exists.

    Args:
        path: the target path.
        content: the file content.
        encoding: text encoding.

    Returns:
        The path written.

    Raises:
        FileExistsError: when the path already exists (use safe_modify).
    """
    if os.path.exists(path):
        raise FileExistsError(
            f"refusing to clobber existing path: {path} "
            f"(classify={classify(path)}); inspect it and use safe_modify, "
            f"or justify an explicit REPLACE")
    with open(path, "w", encoding=encoding) as f:
        f.write(content)
    return path


def safe_modify(path: str, transform: Callable[[str], str], *,
                encoding: str = "utf-8") -> str:
    """Modify an EXISTING file via a transform of its current contents.

    Args:
        path: the target path.
        transform: fn(existing_text) -> new_text.
        encoding: text encoding.

    Returns:
        The path written.

    Raises:
        FileNotFoundError: when the path does not exist (use safe_create).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"cannot modify a non-existent path: {path} (use safe_create)")
    with open(path, encoding=encoding) as f:
        existing = f.read()
    with open(path, "w", encoding=encoding) as f:
        f.write(transform(existing))
    return path
