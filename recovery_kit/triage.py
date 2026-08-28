"""Intake record -> case class + feasibility verdict + attempt plan."""
from __future__ import annotations

import json
from pathlib import Path

from . import commands
from .intake import load_intake
from .space import THROUGHPUT_PRESETS, estimate, verdict


def classify(facts: dict) -> str:
    if str(facts.get("hardware_or_software", "")).lower().startswith("hw") \
            and facts.get("seed_words_remembered", "0") == "0":
        return commands.CLASS_D
    if str(facts.get("has_wallet_file", "")).lower() in ("y", "yes", "true"):
        # corrupted vs passphrase: operator confirms on call; default A if file opens
        return commands.CLASS_A if not facts.get("file_corrupted") else commands.CLASS_C
    if int(facts.get("seed_words_remembered", "0") or 0) > 0:
        return commands.CLASS_B
    return commands.CLASS_C


def triage_case(intake_path: Path) -> dict:
    rec = load_intake(intake_path)
    if not rec.get("gate_cleared"):
        return {"status": "BLOCKED — clear the ownership gate first (intake.py)"}
    facts = rec.get("case_facts", {})
    klass = classify(facts)
    out = {"case_id": rec["case_id"], "class": klass}
    if klass == commands.CLASS_B:
        n = int(facts.get("words_total", 12) or 12)
        known = int(facts.get("seed_words_remembered", 0) or 0)
        slots = ["word"] * known + ["?"] * (n - known)   # operator refines w/ prefixes
        est = estimate(slots, throughput=THROUGHPUT_PRESETS["gpu-flagship"])
        out.update({"slots_placeholder": slots, "estimate": est,
                    "verdict": verdict(est)})
    elif klass == commands.CLASS_A:
        out["plan"] = commands.gen_class_a(rec["case_id"],
                                           base_words=["<base>"], years=["1990"],
                                           symbols=["!"])
    elif klass == commands.CLASS_C:
        out["plan"] = commands.gen_class_c(rec["case_id"], "<file>")
    else:
        out["plan"] = commands.gen_class_d(rec["case_id"], "<device>")
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Triage an intake record")
    ap.add_argument("intake_json", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    result = triage_case(args.intake_json)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
