"""Intake + ownership-proof gate. Produces cases/<id>/intake.json.

GATE RULE: work may only begin when every GATE item is True and zero
DISQUALIFIERS fire. This module never handles key material — it records
only that the client ATTESTED items, which the operator verifies live
on a recorded screen-share before clearing the gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

GATE_ITEMS = {
    "identity_verified":     "Gov-ID matched to face on live video call",
    "tx_history_test":       "Client correctly stated >=2 facts only the owner would know "
                             "(last tx amount/date, address prefix, exchange used)",
    "partial_possession":    "Client typed remembered seed words / passphrase fragments "
                             "FROM MEMORY on the call (not read from a file)",
    "wallet_provenance":     "Provenance evidence: install dates, config files, purchase/"
                             "registration emails, old backups with matching metadata",
    "estate_docs_if_dead":   "Estates only: death certificate + probate/will + executor ID",
    "engagement_signed":     "Written engagement terms signed (scope, warranty of ownership, "
                             "indemnity, refusal rights, data-deletion policy)",
}
DISQUALIFIERS = {
    "no_video":        "Refuses live video identity check",
    "third_party":     "\"Helping a friend\" who cannot appear; urgency pressure",
    "stolen_device":   "Device/wallet reported lost-stolen or seized by police",
    "chain_flags":     "Addresses linked to known exploits/thefts (basic chain check)",
    "custody_demand":  "Demands you hold keys/recovered funds yourself",
    "inconsistent":    "Story changed between intake and verification call",
}


def run_intake(case_id: str, out_dir: Path = Path("cases")) -> dict:
    rec = {"case_id": case_id,
           "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "gate": {}, "disqualifiers": [], "case_facts": {}}
    print(f"=== INTAKE {case_id} ===  (operator fills during/after video call)")
    for k, q in GATE_ITEMS.items():
        rec["gate"][k] = input(f"[gate] {q} ... verified? [y/N] ").strip().lower() == "y"
    for k, q in DISQUALIFIERS.items():
        if input(f"[red-flag] {q} ... present? [y/N] ").strip().lower() == "y":
            rec["disqualifiers"].append(k)
    for k in ("contact", "jurisdiction", "wallet_type", "has_wallet_file",
              "seed_words_remembered", "words_total", "passphrase_hints",
              "value_usd_estimate", "hardware_or_software"):
        v = input(f"[fact] {k}: ").strip()
        rec["case_facts"][k] = v
    rec["gate_cleared"] = all(rec["gate"].values()) and not rec["disqualifiers"]
    d = out_dir / case_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "intake.json").write_text(json.dumps(rec, indent=2))
    print(f"\nGATE STATUS: {'CLEARED' if rec['gate_cleared'] else 'BLOCKED'}"
          f" -> {d/'intake.json'}")
    return rec


def load_intake(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ownership-proof intake runner")
    ap.add_argument("case_id")
    ap.add_argument("--from-json", type=Path, help="skip prompts; validate existing record")
    args = ap.parse_args(argv)
    if args.from_json:
        rec = load_intake(args.from_json)
        ok = all(rec.get("gate", {}).values()) and not rec.get("disqualifiers")
        print(f"GATE STATUS: {'CLEARED' if ok else 'BLOCKED'} ({args.from_json})")
        return 0 if ok else 2
    run_intake(args.case_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
