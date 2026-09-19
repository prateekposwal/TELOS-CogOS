"""
Dependency-free asymmetric ATTESTATION for the external witness service.

WHY THIS EXISTS (do not confuse it with a write credential):
    The external trust anchor authenticates the local *writer* with a shared
    bearer token. A token is symmetric: an attacker who compromises the local
    producer can read it and could then forge a witness answer if the answer
    were only "signed" with that same secret. To let a LOCAL verifier confirm
    that an answer genuinely came from the witness WITHOUT giving the producer a
    forging capability, the witness holds an ASYMMETRIC signing key and publishes
    only its PUBLIC key. A local compromise of every producer-side credential
    therefore cannot forge a witness answer: the private key never leaves the
    witness process.

IMPLEMENTATION (stdlib only, no third-party crypto):
    RSA with PKCS#1 v1.5 + SHA-256 (RSASSA-PKCS1-v1_5). Python's standard library
    has no asymmetric primitive, so the minimum is implemented here directly on
    integers: Miller-Rabin prime generation, a 2048-bit default modulus with
    e=65537, EMSA-PKCS1-v1_5 encoding, and signature verification. This is a
    genuine public-key signature (the private exponent is never needed to verify)
    but it is deliberately NOT claimed to be HSM-grade key custody: a same-account
    deployment leaves the private key file readable by the account.

THREAT MODEL (honest):
    * Attacker with the ENTIRE local producer (files, envelope/checksum, bearer
      token, historical valid records) but NOT the witness private key:
      cannot forge an attestation (verification fails) and cannot lower the
      server-side sequence floor.
    * Attacker who ALSO controls the witness host/key file: out of scope.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from typing import Any, Dict, List, Optional

#: The only supported attestation algorithm.
ATTEST_ALG = "rsa-pkcs1v15-sha256"

#: The production default modulus size (bits).
DEFAULT_KEY_BITS = 2048

#: ASN.1 DER prefix for a SHA-256 DigestInfo (RFC 8017, section 9.2).
_SHA256_DIGESTINFO_PREFIX = bytes.fromhex(
    "3031300d060960864801650304020105000420")

#: Small primes used to cheaply reject most Miller-Rabin candidates.
_SMALL_PRIMES = (
    2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67,
    71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113, 127, 131, 137, 139, 149,
    151, 157, 163, 167, 173, 179, 181, 191, 193, 197, 199, 211, 223, 227, 229,
    233, 239, 241, 251, 257, 263, 269, 271, 277, 281, 283, 293, 307, 311, 313,
    317, 331, 337, 347, 349, 353, 359, 367, 373, 379, 383, 389, 397, 401, 409,
    419, 421, 431, 433, 439, 443, 449, 457, 461, 463, 467, 479, 487, 491, 499,
    503, 509, 521, 523, 541, 547, 557, 563, 569, 571, 577, 587, 593, 599, 601,
    607, 613, 617, 619, 631, 641, 643, 647, 653, 659, 661, 673, 677, 683, 691,
    701, 709, 719, 727, 733, 739, 743, 751, 757, 761, 769, 773, 787, 797, 809,
    811, 821, 823, 827, 829, 839, 853, 857, 859, 863, 877, 881, 883, 887, 907,
    911, 919, 929, 937, 941, 947, 953, 967, 971, 977, 983, 991, 997,
)


def canonical_json_bytes(obj: Any) -> bytes:
    """Canonical, deterministic JSON bytes for an attested object.

    Byte-identical to ``trust_anchor.canonical_witness_bytes`` (sorted keys,
    compact separators, ASCII, no NaN) so the witness signs exactly the record
    bytes the provider hashes.

    Args:
        obj: the JSON-serializable object.

    Returns:
        UTF-8 encoded canonical JSON bytes.
    """
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _gcd(a: int, b: int) -> int:
    """Euclid's greatest common divisor.

    Args:
        a: first integer.
        b: second integer.

    Returns:
        The non-negative gcd of ``a`` and ``b``.
    """
    while b:
        a, b = b, a % b
    return a


def _is_probable_prime(n: int, rounds: int = 40) -> bool:
    """Miller-Rabin primality test with deterministic small-prime sieving.

    Args:
        n: the candidate integer.
        rounds: the number of random Miller-Rabin rounds.

    Returns:
        True when ``n`` passes every round (probable prime), else False.
    """
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n % p == 0:
            return n == p
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = (x * x) % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _generate_prime(bits: int) -> int:
    """Generate a probable prime with exactly ``bits`` bits.

    Args:
        bits: the target bit length (must be >= 8).

    Returns:
        A probable prime with the top two bits set.
    """
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | (1 << 1) | 1
        if _is_probable_prime(candidate):
            return candidate


def generate_private_key(bits: int = DEFAULT_KEY_BITS) -> Dict[str, Any]:
    """Generate an RSA private key as a serializable mapping.

    Args:
        bits: the modulus size in bits (default :data:`DEFAULT_KEY_BITS`).

    Returns:
        A mapping ``{"alg", "bits", "n", "e", "d"}`` with hex integers.

    Raises:
        ValueError: when ``bits`` is too small for a SHA-256 RSA signature.
    """
    if bits < 1024:
        raise ValueError("RSA modulus must be at least 1024 bits")
    e = 65537
    half = bits // 2
    while True:
        p = _generate_prime(half)
        q = _generate_prime(bits - half)
        if p == q:
            continue
        phi = (p - 1) * (q - 1)
        if _gcd(e, phi) != 1:
            continue
        n = p * q
        d = pow(e, -1, phi)
        if n.bit_length() != bits:
            continue
        return {"alg": ATTEST_ALG, "bits": int(bits),
                "n": format(n, "x"), "e": int(e), "d": format(d, "x")}


def key_id(public: Dict[str, Any]) -> str:
    """A short stable identifier for a public key.

    Args:
        public: a public-key mapping with a hex ``n``.

    Returns:
        The first 16 hex chars of sha256 over the modulus bytes.
    """
    n = int(str(public["n"]), 16)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return hashlib.sha256(raw).hexdigest()[:16]


def public_from_private(private: Dict[str, Any]) -> Dict[str, Any]:
    """Derive the publishable public key from a private key.

    Args:
        private: a private-key mapping.

    Returns:
        A public-key mapping ``{"alg", "n", "e", "key_id"}``.
    """
    pub = {"alg": str(private.get("alg", ATTEST_ALG)),
           "n": str(private["n"]), "e": int(private["e"])}
    pub["key_id"] = key_id(pub)
    return pub


def save_private_key(path: str, private: Dict[str, Any]) -> None:
    """Persist a private key with owner-only permissions.

    Args:
        path: the destination key-file path.
        private: the private-key mapping.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(private, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_private_key(path: str) -> Dict[str, Any]:
    """Load a private key from disk.

    Args:
        path: the key-file path.

    Returns:
        The validated private-key mapping.

    Raises:
        FileNotFoundError: when the key file does not exist.
        ValueError: when the file is not a valid private-key mapping.
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict) or "n" not in raw or "d" not in raw:
        raise ValueError(f"{path!r} is not a valid RSA private key")
    return raw


def save_public_key(path: str, public: Dict[str, Any]) -> None:
    """Persist a public key (world-readable is fine; it is public).

    Args:
        path: the destination path.
        public: the public-key mapping.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(public, f, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())


def load_public_key(path: str) -> Dict[str, Any]:
    """Load a public key from disk.

    Args:
        path: the path to the public-key JSON.

    Returns:
        The validated public-key mapping.

    Raises:
        ValueError: when the file is not a valid public-key mapping.
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict) or "n" not in raw or "e" not in raw:
        raise ValueError(f"{path!r} is not a valid RSA public key")
    return raw


def _emsa_pkcs1_v15_sha256(message: bytes, klen: int) -> bytes:
    """EMSA-PKCS1-v1_5 encoding of a SHA-256 digest (RFC 8017, 9.2).

    Args:
        message: the message bytes to sign/verify.
        klen: the RSA modulus length in bytes.

    Returns:
        The encoded message (EM) of length ``klen``.

    Raises:
        ValueError: when the modulus is too small for the encoding.
    """
    digest = hashlib.sha256(message).digest()
    t = _SHA256_DIGESTINFO_PREFIX + digest
    if klen < len(t) + 11:
        raise ValueError(
            f"RSA modulus too small ({klen} bytes) for PKCS#1 v1.5 SHA-256")
    ps = b"\xff" * (klen - len(t) - 3)
    return b"\x00\x01" + ps + b"\x00" + t


def sign_record(record: Dict[str, Any],
                private: Dict[str, Any]) -> Dict[str, Any]:
    """Attest a witnessed record with the witness's private key.

    Args:
        record: the record mapping to attest (canonicalized internally).
        private: the private-key mapping.

    Returns:
        An attestation mapping ``{"alg", "key_id", "sig"}`` where ``sig`` is the
        lowercase hex RSA signature over ``canonical_json_bytes(record)``.
    """
    n = int(str(private["n"]), 16)
    d = int(str(private["d"]), 16)
    klen = (n.bit_length() + 7) // 8
    em = _emsa_pkcs1_v15_sha256(canonical_json_bytes(record), klen)
    m = int.from_bytes(em, "big")
    signature = pow(m, d, n).to_bytes(klen, "big")
    pub = {"alg": str(private.get("alg", ATTEST_ALG)),
           "n": str(private["n"]), "e": int(private["e"])}
    return {"alg": ATTEST_ALG, "key_id": key_id(pub),
            "sig": signature.hex()}


def verify_attestation(public: Dict[str, Any], record: Dict[str, Any],
                       attestation: Optional[Dict[str, Any]]) -> bool:
    """Verify a witness attestation against a pinned public key.

    Args:
        public: the trusted public-key mapping (``n`` + ``e``).
        record: the record mapping the attestation covers.
        attestation: the attestation mapping from the witness (or None).

    Returns:
        True only when the attestation is present, names the same algorithm and
        key, and its signature verifies over the canonical record bytes.
    """
    if not isinstance(attestation, dict):
        return False
    if str(attestation.get("alg")) != ATTEST_ALG:
        return False
    if str(attestation.get("key_id")) != key_id(public):
        return False
    signature_hex = attestation.get("sig")
    if not isinstance(signature_hex, str):
        return False
    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError:
        return False
    n = int(str(public["n"]), 16)
    e = int(str(public["e"]), 10)
    klen = (n.bit_length() + 7) // 8
    if len(signature) != klen:
        return False
    m = pow(int.from_bytes(signature, "big"), e, n)
    em = m.to_bytes(klen, "big")
    try:
        expected = _emsa_pkcs1_v15_sha256(canonical_json_bytes(record), klen)
    except ValueError:
        return False
    return hmac.compare_digest(em, expected)


__all__: List[str] = [
    "ATTEST_ALG", "DEFAULT_KEY_BITS", "canonical_json_bytes",
    "generate_private_key", "public_from_private", "key_id",
    "save_private_key", "load_private_key", "save_public_key", "load_public_key",
    "sign_record", "verify_attestation",
]
