"""Safe-write guard tests — the file-overwrite invariant."""

import os

import pytest

from telos.tools import safe_write


def test_classify_create_vs_replace(tmp_path):
    p = str(tmp_path / "f.txt")
    assert safe_write.classify(p) == "CREATE"
    open(p, "w").write("x")
    assert safe_write.classify(p) == "REPLACE"


def test_safe_create_refuses_to_clobber(tmp_path):
    p = str(tmp_path / "f.txt")
    safe_write.safe_create(p, "hello")
    with pytest.raises(FileExistsError):
        safe_write.safe_create(p, "world")      # refuses
    assert open(p).read() == "hello"            # untouched


def test_safe_modify_requires_existing(tmp_path):
    p = str(tmp_path / "f.txt")
    with pytest.raises(FileNotFoundError):
        safe_write.safe_modify(p, lambda s: s + "!")
    safe_write.safe_create(p, "a")
    safe_write.safe_modify(p, lambda s: s + "b")
    assert open(p).read() == "ab"
