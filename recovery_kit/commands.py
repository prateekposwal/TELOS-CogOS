"""btcrecover / hashcat command generator per case class.

SKELETON HONESTY (Lambda-2.3): btcrecover flags drift between releases.
Every generated command carries a TODO(verify) marker — the operator MUST
check against https://btcrecover.readthedocs.io for the pinned version
before launching. Generated files are plans, not gospel.
"""
from __future__ import annotations

CLASS_A = "passphrase-forgotten"   # wallet.dat / Electrum / BIP39 passphrase
CLASS_B = "partial-seed"           # some words known/guessable
CLASS_C = "corrupted-file"         # parsing/forensics, no brute force
CLASS_D = "hardware-pin"           # device-limited; physical, no software bypass


def gen_class_a(case_id: str, base_words: list[str], years: list[str],
                symbols: list[str]) -> str:
    """Tokenlist from structure hints: Word + year + symbol (+typos)."""
    tokens = [f"{w} {y} {s}" for w in base_words for y in years for s in symbols]
    token_file = f"cases/{case_id}/tokens.txt"
    plan = f"""# CLASS A ({CLASS_A}) — case {case_id}
# 1) Write token file ({len(tokens)} base lines; btcrecover applies mutations)
cat > cases/{case_id}/tokens.txt <<'TOKENS'
{chr(10).join(tokens)}
TOKENS
# 2) Run (TODO(verify): flags against your pinned btcrecover version)
python3 btcrecover.py --wallet cases/{case_id}/wallet.dat \\
  --tokenlist {token_file} \\
  --typo-case --max-typos 2 --no-progress
# GPU alternative once space is confirmed >1e8:
#   export hash rules via tokenlist -> hashcat -m 22911? (Electrum) or
#   hashcat -m 9645 family for BIP39; benchmark FIRST (Lambda-1.2).
"""
    return plan


def gen_class_b(case_id: str, slots: list[str], address_hint: str | None,
                unknown_order: int = 0) -> str:
    """Seed reconstruction. slots use the space.py DSL."""
    n = len(slots)
    order_note = (f"# {unknown_order} words have UNKNOWN ORDER (x{unknown_order}!)\n"
                  if unknown_order else "")
    addr = address_hint or "<client-known-address — REQUIRED to confirm a hit>"
    return f"""# CLASS B ({CLASS_B}) — case {case_id}, {n}-word phrase
{order_note}# Feasibility first:
#   python3 -m recovery_kit.cli estimate-space {' '.join('--slot ' + s for s in slots)} \\
#     {'--unknown-order %d ' % unknown_order if unknown_order else ''}--value-usd <V>
# Attempt (btcrecover seed mode; TODO(verify) flags for pinned version):
python3 btcrecover.py --seed \\
  --wallet-addresses {addr} \\
  --mnemonic-language en \\
  --tokenlist cases/{case_id}/seed_tokens.txt --no-progress
# seed_tokens.txt encodes known words in order; wildcards per btcrecover docs.
# NEVER let the client paste full seed material into chat/email — screen-share
# only, client-side execution where possible.
"""


def gen_class_c(case_id: str, filename: str) -> str:
    """Corrupted file: triage before any brute force."""
    return f"""# CLASS C ({CLASS_C}) — case {case_id}: {filename}
# 1) Integrity: file(1), size vs expected format, magic bytes
file '{filename}' && xxd '{filename}' | head -40
# 2) Identify format family: Core wallet.dat (BerkeleyDB), Multibit .wallet
#    (AES keyring), Electrum JSON, Bitcoin Wallet for Android backup
# 3) Parse/recover keys WITHOUT password if format allows (e.g., unencrypted
#    key material, salvage mode); pywallet.py dumpwallet as starting point
# 4) Only then consider brute force on whatever is actually encrypted.
"""


def gen_class_d(case_id: str, device: str) -> str:
    """Hardware PIN: honest scope — we do NOT bypass secure elements."""
    return f"""# CLASS D ({CLASS_D}) — case {case_id}: {device}
# Honest scope: no software bypass of secure-element rate limiting exists.
# Options to advise client on: official-vendor wipe+restore-from-seed flows,
# vendor support channels with proof of purchase, passphrase-vs-PIN confusion
# triage. If they lost the SEED too and PIN is unknown -> likely unrecoverable;
# say so early (Lambda-6.5 falsification gate). Do not accept fee hopes here.
"""


GENERATORS = {CLASS_A: lambda c, **k: gen_class_a(c, k["base_words"], k["years"], k["symbols"]),
              CLASS_B: lambda c, **k: gen_class_b(c, k["slots"], k.get("address_hint"), k.get("unknown_order", 0)),
              CLASS_C: lambda c, **k: gen_class_c(c, k["filename"]),
              CLASS_D: lambda c, **k: gen_class_d(c, k["device"])}


def main(argv=None):
    import argparse, json
    ap = argparse.ArgumentParser(description="Attempt-plan generator")
    ap.add_argument("case_id")
    ap.add_argument("case_class", choices=[CLASS_A, CLASS_B, CLASS_C, CLASS_D])
    ap.add_argument("--params", default="{}", help="JSON params for the class")
    args = ap.parse_args(argv)
    params = json.loads(args.params)
    print(GENERATORS[args.case_class](args.case_id, **params))


if __name__ == "__main__":
    main()
