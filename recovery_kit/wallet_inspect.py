"""Wallet-format identification for the Class C (corrupted-file) workflow.

INSPECTION ONLY — this module never extracts, derives, or returns key
material. Given an encrypted artifact's bytes (wallet.dat, Multibit .wallet,
Electrum file, Android backup) it identifies the format family via magic
bytes / structural heuristics and reports whether the content looks
encrypted, so the operator can pick the right plan in
recovery_kit.commands.gen_class_c.

Trust boundary (Lambda-6.7): bytes are analyzed in memory and discarded —
nothing is persisted or logged. No plaintext key material should EVER reach
this function; if a caller uploads an unencrypted JSON wallet this still
works (it detects plaintext) but that is the caller's error and we do not
store it either way.
"""
from __future__ import annotations

import json

# Sizes, not secrets — magic constants for format identification.
MAX_INSPECT_BYTES = 64_000_000        # hard cap for upload analysis (64 MB)
BDB_MAGICS = (0x00053162, 0x00061561)  # BerkeleyDB 3.x magic bytes (LE, 4-byte)
PK_ZIP = b"PK\x03\x04"                 # ZIP local file header (Android backups)


def _bdb_magic(data: bytes) -> bool:
    if len(data) < 4:
        return False
    for m in BDB_MAGICS:
        if int.from_bytes(data[:4], "little") == m:
            return True
    return False


def _looks_utf8_json(data: bytes) -> bool:
    try:
        text = data.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return False
    text = text.lstrip("\ufeff \t\r\n")
    if not text or text[0] not in "{[":
        return False
    try:
        json.loads(text)
        return True
    except ValueError:
        return False


def _electrum_json(data: bytes) -> dict | None:
    """Return {} marker info if this is an Electrum-style JSON wallet."""
    try:
        text = data.decode("utf-8")
        obj = json.loads(text.lstrip("\ufeff \t\r\n"))
    except (ValueError, UnicodeDecodeError):
        return None
    if isinstance(obj, dict):
        keys = " ".join(obj.keys())
        if "keystore" in keys or "seed_version" in keys or "wallet_type" in keys:
            return {"has_keystore": "keystore" in keys,
                    "seed_version": obj.get("seed_version"),
                    "wallet_type": obj.get("wallet_type")}
    return None


def _zip_namelist(data: bytes) -> list[str]:
    """Return first entries of a ZIP central/local directory if present."""
    names = []
    offset = 0
    while len(names) < 6:
        i = data.find(PK_ZIP, offset)
        if i < 0:
            break
        if i + 30 <= len(data):
            fname_len = int.from_bytes(data[i + 26:i + 28], "little")
            names.append(data[i + 30:i + 30 + fname_len].decode("utf-8", "replace"))
        offset = i + 4
    return names


def _printable_ratio(data: bytes) -> float:
    if not data:
        return 1.0
    sample = data[:8192]
    printable = sum(1 for b in sample if 32 <= b <= 126 or b in (9, 10, 13))
    return printable / len(sample)


def inspect_wallet_file(data: bytes, filename: str = "") -> dict:
    """Identify format family of an encrypted/obscure wallet artifact.

    Returns a report dict; NEVER includes key material or file contents.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("data must be bytes")
    data = bytes(data)
    if len(data) == 0:
        raise ValueError("empty file")
    if len(data) > MAX_INSPECT_BYTES:
        raise ValueError("file too large (max %d bytes)" % MAX_INSPECT_BYTES)

    size = len(data)
    digest = __import__("hashlib").sha256(data).hexdigest()[:16]  # prefix only
    printable = _printable_ratio(data)
    json_info = _electrum_json(data)
    names = _zip_namelist(data) if data.startswith(PK_ZIP) else []
    bdb = _bdb_magic(data)

    if bdb:
        family = "bitcoin-core-wallet.dat"
        evidence = "BerkeleyDB magic bytes 0x00053162/0x00061561"
        encrypted = True
        detail = ("BerkeleyDB container — likely Bitcoin Core wallet.dat. "
                  "Encrypted only if the wallet had a passphrase; parse with "
                  "BerkeleyDB tools first, then decrypt.")
    elif json_info is not None:
        family = "electrum-json"
        evidence = "valid JSON with keystore/seed_version/wallet_type keys"
        encrypted = False
        detail = ("Plaintext Electrum wallet file detected. If this reached the "
                  "server it is a transport violation: never send unencrypted "
                  "key material. Analyze locally only; do not persist.")
    elif names:
        family = "android-backup-zip"
        evidence = "ZIP container (%s)" % ", ".join(names[:3])
        encrypted = True
        detail = ("Android bitcoin-wallet backup archive — ZIP of encrypted "
                  "seed blob; needs app-specific decrypt flow.")
    elif printable < 0.3:
        family = "unknown-binary"
        evidence = "low printable-byte ratio (%.1f%%)" % (printable * 100)
        encrypted = True
        detail = ("Binary with low text ratio — likely encrypted/compressed. "
                  "Format family unknown; try file(1) + xxd locally.")
    else:
        family = "plaintext-json-or-text"
        evidence = "high printable-byte ratio (%.1f%%)" % (printable * 100)
        encrypted = printable < 0.85
        detail = ("Text-like content. If it is a JSON wallet without encryption "
                  "it must not be uploaded — keep local. Otherwise likely a "
                  "config/export file.")

    return {
        "filename": filename,
        "size_bytes": size,
        "sha256_prefix": digest,          # first 16 hex chars only, dedupe not secret
        "format_family": family,
        "evidence": evidence,
        "looks_encrypted": encrypted,
        "detail": detail,
        "recommended_class": "C",
        "analyzed_in_memory": True,
    }
