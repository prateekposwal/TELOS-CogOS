"""wallet_inspect + /api/wallet-inspect tests — synthetic fixtures only."""
import json
import threading
import urllib.request

import pytest

from recovery_kit.wallet_inspect import (MAX_INSPECT_BYTES,
                                         inspect_wallet_file)


# ── unit tests for the detection module ─────────────────────────────────────

def test_bdb_wallet_dat():
    fake_bdb = b"\x62\x31\x05\x00" + b"\x00" * 40  # 0x00053162 LE
    rep = inspect_wallet_file(fake_bdb, "wallet.dat")
    assert rep["format_family"] == "bitcoin-core-wallet.dat"
    assert rep["looks_encrypted"] is True
    assert rep["recommended_class"] == "C"
    assert rep["sha256_prefix"]  # 16-hex prefix present


def test_electrum_json_detected_plaintext():
    payload = json.dumps({"seed_version": 11, "keystore": {},
                          "wallet_type": "standard"}).encode()
    rep = inspect_wallet_file(payload, "default_wallet")
    assert rep["format_family"] == "electrum-json"
    assert rep["looks_encrypted"] is False
    assert "transport violation" in rep["detail"].lower()


def test_android_backup_zip():
    zip_like = b"PK\x03\x04" + b"\x00" * 26 + b"\x06\x00" + b"wallet" + b"\x00" * 10
    rep = inspect_wallet_file(zip_like, "backup.tar")
    assert rep["format_family"] == "android-backup-zip"
    assert rep["looks_encrypted"] is True


def test_unknown_binary_looks_encrypted():
    rep = inspect_wallet_file(b"\x00\xff\x01\x02\x03\x00\xff\xee\xdd\xcc", "x")
    assert rep["format_family"] == "unknown-binary"
    assert rep["looks_encrypted"] is True


def test_empty_and_oversize_rejected():
    with pytest.raises(ValueError):
        inspect_wallet_file(b"")
    with pytest.raises(ValueError):
        inspect_wallet_file(b"\x00" * (MAX_INSPECT_BYTES + 1))


def test_no_key_material_in_report():
    secret = b"\x00\x01secret-key-material-\xff\xfe"
    rep = inspect_wallet_file(secret, "blob")
    blob = json.dumps(rep)
    assert "secret-key-material" not in blob


# ── integration: endpoint over an ephemeral server ─────────────────────────

def _start_test_server():
    from recovery_kit.server import create_server
    httpd = create_server(port=0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, t


def test_wallet_inspect_endpoint_raw_body():
    from recovery_kit.server import RecoveryKitHandler  # noqa: ensure import
    httpd, t = _start_test_server()
    try:
        port = httpd.server_address[1]
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/wallet-inspect" % port,
            data=b"\x62\x31\x05\x00" + b"\x00" * 40,
            headers={"Content-Type": "application/octet-stream",
                     "X-Filename": "wallet.dat"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            body = json.loads(resp.read().decode())
            assert body["report"]["format_family"] == "bitcoin-core-wallet.dat"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_wallet_page_served():
    from recovery_kit.server import create_server
    httpd, t = _start_test_server()
    try:
        port = httpd.server_address[1]
        with urllib.request.urlopen("http://127.0.0.1:%d/wallet" % port) as resp:
            html = resp.read().decode()
            assert resp.status == 200
            assert "NEVER type or paste seed words" in html
            assert "wallet-inspect" in html
    finally:
        httpd.shutdown()
        httpd.server_close()
