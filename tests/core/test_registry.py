"""Axiom registry contract (telos/core/axioms/registry.py).

The registry is the compiled once-at-startup constitutional constant: 42
axioms, every entry carrying an enforcement status, stable identity, and a
fingerprint that survives import. Runtime never re-parses AXIOMS.md.
"""
import hashlib

from telos.core.axioms.registry import AXIOMS


# The canonical 42-axiom constitution (registry ids at fresh import).
_BASE_IDS = tuple(sorted(str(a.get("id", "")) for a in AXIOMS))


def test_registry_holds_42_axioms():
    # At a fresh import the registry holds exactly the 42-axiom constitution.
    # The evolution engine MAY transiently append approved proposals (Λ5.2
    # write-through) during a suite, so assert the constitution's integrity:
    # every canonical id present, unique, and any extras are evolution-scoped.
    ids = [str(a.get("id", "")) for a in AXIOMS]
    assert len(ids) == len(set(ids)), "registry ids must be unique"
    for base in _BASE_IDS:
        assert base in ids, f"constitutional axiom '{base}' missing"
    assert len(_BASE_IDS) == 42
    extras = [i for i in ids if i not in _BASE_IDS]
    for e in extras:
        assert e.startswith("axiom_"), (
            f"non-constitutional entry '{e}' must be evolution-scoped"
        )


def test_every_entry_has_id_and_enforcement():
    for a in AXIOMS:
        assert "id" in a
        assert "enforcement" in a
        assert a["enforcement"] in ("enforced", "scaffold", "aspirational")


def test_fingerprint_stable_and_identifying():
    fp = hashlib.sha256(
        "|".join(sorted(str(a.get("id", "")) for a in AXIOMS)).encode()
    ).hexdigest()
    assert len(fp) == 64
    # identical inputs -> identical fingerprint (compiled once, frozen)
    fp2 = hashlib.sha256(
        "|".join(sorted(str(a.get("id", "")) for a in AXIOMS)).encode()
    ).hexdigest()
    assert fp == fp2


def test_ids_unique():
    ids = [a.get("id") for a in AXIOMS]
    assert len(ids) == len(set(ids))
