"""Contract tests for GenesisAnchor — the genesis identity anchor and its
creator/user recognition."""
import pytest

from telos.core.genesis import GenesisAnchor, ANCHOR


def _anchor():
    from telos.core.genesis import GenesisAnchor
    return GenesisAnchor()


def test_recognizes_creator_names(monkeypatch):
    monkeypatch.setenv("TELOS_CREATOR_NAME", "private-phrase")
    a = GenesisAnchor()
    assert a.recognize("Prateek") is True
    assert a.recognize("private-phrase") is True   # case-insensitive
    assert a.recognize("PRIVATE-PHRASE") is True


def test_private_name_is_read_from_env_not_hardcoded():
    # No secret lives in the source; without the env it is empty.
    a = GenesisAnchor()
    assert a.creator_name_for_me == ""


def test_recognizes_others_as_not_creator():
    a = _anchor()
    assert a.recognize("someone_else") is False
    assert a.recognize("") is False
    assert a.recognize(None) is False


def test_name_for_creator_uses_personal_name():
    a = _anchor()
    n = a.name_for(is_creator=True)
    assert isinstance(n, str) and n


def test_name_for_non_creator_uses_public_name():
    a = _anchor()
    n = a.name_for(is_creator=False)
    assert isinstance(n, str) and n


def test_module_anchor_is_instantiated():
    assert isinstance(ANCHOR, GenesisAnchor)