"""recovery_kit CLI dispatcher. python3 -m recovery_kit.cli <cmd> ..."""
import sys


def main():
    cmds = {
        "intake": ("recovery_kit.intake", "Ownership-proof intake runner"),
        "estimate-space": ("recovery_kit.space", "BIP-39 search-space estimator"),
        "gen-command": ("recovery_kit.commands", "Attempt-plan generator"),
        "triage": ("recovery_kit.triage", "Classify intake -> feasibility + plan"),
        "benchmark": ("recovery_kit.benchmark", "Measure local search throughput"),
    }
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("usage: python3 -m recovery_kit.cli <cmd> [args]\n"
              "commands:\n" + "\n".join(f"  {k:<16}{v[1]}" for k, v in cmds.items()))
        return 1
    name = sys.argv[1]
    if name not in cmds:
        print(f"unknown command: {name}")
        return 1
    mod_name = cmds[name][0]
    mod = __import__(mod_name, fromlist=["main"])
    sys.argv = [f"{__package__} {name}"] + sys.argv[2:]
    return mod.main() or 0


if __name__ == "__main__":
    sys.exit(main())
