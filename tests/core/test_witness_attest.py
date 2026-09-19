"""
Witness attestation primitives: asymmetric signing, verification, tamper fails.

These lock the property the adversarial boundary depends on: a local attacker
holding every producer-side credential (including the witness WRITE token) still
cannot forge a witness answer, because verification only needs the PUBLIC key.
"""

import json

from telos.core.actions import witness_attest as wa


def _record(seq=1, marker="a"):
    """A minimal attested record."""
    return {"sequence": seq, "state_hash": marker * 64, "evidence_hash": "b" * 64,
            "scope": {"store_id": "s", "producer_id": "telos", "world_id": "w",
                      "capability_id": "*"}}


def test_sign_and_verify_roundtrip():
    """A signature over a record verifies with the derived public key."""
    key = wa.generate_private_key(1024)
    pub = wa.public_from_private(key)
    att = wa.sign_record(_record(), key)
    assert wa.verify_attestation(pub, _record(), att) is True


def test_modified_record_fails_verification():
    """Editing the record invalidates the signature."""
    key = wa.generate_private_key(1024)
    pub = wa.public_from_private(key)
    att = wa.sign_record(_record(marker="a"), key)
    assert wa.verify_attestation(pub, _record(marker="c"), att) is False


def test_forged_signature_fails_verification():
    """A made-up signature does not verify."""
    key = wa.generate_private_key(1024)
    pub = wa.public_from_private(key)
    forged = {"alg": wa.ATTEST_ALG, "key_id": pub["key_id"], "sig": "00" * 128}
    assert wa.verify_attestation(pub, _record(), forged) is False


def test_wrong_key_fails_verification():
    """A signature from another key does not verify against the pinned key."""
    signer = wa.generate_private_key(1024)
    other = wa.public_from_private(wa.generate_private_key(1024))
    att = wa.sign_record(_record(), signer)
    assert wa.verify_attestation(other, _record(), att) is False


def test_missing_attestation_fails_verification():
    """None / non-mapping attestations fail closed."""
    pub = wa.public_from_private(wa.generate_private_key(1024))
    assert wa.verify_attestation(pub, _record(), None) is False
    assert wa.verify_attestation(pub, _record(), "not-a-dict") is False


def test_key_persistence_roundtrip(tmp_path):
    """Private + public keys round-trip through their files."""
    key = wa.generate_private_key(1024)
    kp = tmp_path / "priv.json"
    pp = tmp_path / "pub.json"
    wa.save_private_key(str(kp), key)
    wa.save_public_key(str(pp), wa.public_from_private(key))
    loaded = wa.load_private_key(str(kp))
    att = wa.sign_record(_record(), loaded)
    assert wa.verify_attestation(wa.load_public_key(str(pp)), _record(), att)


def test_private_key_file_is_owner_only(tmp_path):
    """The private key file is written 0600 (not group/world readable)."""
    import os
    import stat
    kp = tmp_path / "priv.json"
    wa.save_private_key(str(kp), wa.generate_private_key(1024))
    mode = stat.S_IMODE(os.stat(str(kp)).st_mode)
    assert mode == 0o600


def test_canonical_bytes_match_trust_anchor_contract():
    """The attested canonicalization is byte-identical to the witness contract."""
    from telos.core.actions.trust_anchor import canonical_witness_bytes
    obj = {"b": 2, "a": [1, 2.5], "s": "x"}
    assert wa.canonical_json_bytes(obj) == canonical_witness_bytes(obj)
    assert b" " not in wa.canonical_json_bytes(obj)


def test_key_id_is_stable_and_key_specific():
    """key_id is deterministic per key and differs across keys."""
    key = wa.generate_private_key(1024)
    pub = wa.public_from_private(key)
    assert wa.key_id(pub) == pub["key_id"]
    assert wa.key_id(pub) != wa.key_id(
        wa.public_from_private(wa.generate_private_key(1024)))


def test_attestation_json_serializable():
    """An attestation is plain JSON-safe data (no exotic types on the wire)."""
    key = wa.generate_private_key(1024)
    att = wa.sign_record(_record(), key)
    assert json.loads(json.dumps(att)) == att
