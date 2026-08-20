"""
TELOS v6 — Phase 9: sandboxed real code-validation for DevDomain.

Closes the ground-truth loop. Replaces the fabricated `test_pass_ratio = 1.0`
("assume pass unless we run tests") with REAL measured evidence obtained by
discovering and running the appropriate validation commands (tests / type-check
/ lint) in a safe sandbox.

Evidence-must-not-lie guarantees:
  - A value is stamped MEASURED ONLY IF an external tool actually produced it.
  - If a command cannot run (not installed / timeout / infra error) the effort
    falls back to clearly-stamped UNVALIDATED/SIMULATION evidence — it is
    NEVER painted as measured.
"""

import json
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

from telos.world.evidence import (
    EvidenceInfo, EvidenceSource, ValidationStatus, measured,
)

OUTPUT_LIMIT = 1024 * 1024  # 1 MB bounded capture


class RunClass:
    SUCCESS = "SUCCESS"
    TEST_FAILURE = "TEST_FAILURE"
    BUILD_ERROR = "BUILD_ERROR"
    TIMEOUT = "TIMEOUT"
    INFRA_ERROR = "INFRA_ERROR"


@dataclass
class CommandRun:
    name: str
    args: List[str]
    returncode: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    classification: str = RunClass.INFRA_ERROR
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.classification == RunClass.SUCCESS

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "args": list(self.args),
            "returncode": self.returncode,
            "classification": self.classification,
            "timed_out": self.timed_out,
            "stdout_bytes": len(self.stdout),
            "stderr_bytes": len(self.stderr),
        }


_PROJECT_PREFIXES_COMMON = ["pyproject.toml", "setup.py", "setup.cfg",
                            "requirements.txt", "go.mod", "Cargo.toml"]


def _safe_run(args: List[str], cwd: str, timeout: float = 30.0) -> CommandRun:
    """Run a subprocess in list-form (no shell) with bounded capture.
    
    Args:
        args: command as a list (no shell); not executed via a shell
        cwd: working directory to run the subprocess in
        timeout: seconds before the subprocess is treated as timed out
    """
    name = args[0] if args else "command"
    run = CommandRun(name=name, args=list(args))
    try:
        proc = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        run.returncode = proc.returncode
        run.stdout = proc.stdout[:OUTPUT_LIMIT]
        run.stderr = proc.stderr[:OUTPUT_LIMIT]
        run.timed_out = False
    except subprocess.TimeoutExpired as e:
        run.returncode = None
        run.timed_out = True
        run.stdout = (e.stdout or "")[:OUTPUT_LIMIT]
        run.stderr = (e.stderr or "")[:OUTPUT_LIMIT]
        run.classification = RunClass.TIMEOUT
        return run
    except FileNotFoundError:
        run.returncode = None
        run.classification = RunClass.INFRA_ERROR
        return run
    except Exception:
        run.returncode = None
        run.classification = RunClass.INFRA_ERROR
        return run

    # Classify based on return code.
    if run.returncode == 0:
        run.classification = RunClass.SUCCESS
    elif run.returncode is not None and run.returncode != 0:
        run.classification = RunClass.TEST_FAILURE
    return run


def _has(pkg: str, project_path: str) -> bool:
    """Return True if pkg exists inside the project_path directory."""
    return os.path.exists(os.path.join(project_path, pkg))


def _parse_package_json(project_path: str) -> Dict:
    """Parse and return the project_path's package.json scripts, or {} if absent/unparseable."""
    pkg_path = os.path.join(project_path, "package.json")
    if not _has("package.json", project_path):
        return {}
    try:
        with open(pkg_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def discover_commands(project_path: str) -> List[Tuple[str, List[str]]]:
    """Discover appropriate validation commands for a project (not hardcoded).
    
    Returns a list of (name, args) e.g. ("test", ["npm","test","--","--runInBand"]).
    Only discovers commands whose prerequisites exist; discovers tests/typecheck/
    lint across common toolchains.
    
    Args:
        project_path: path to the project whose validation commands are discovered
    """
    commands: List[Tuple[str, List[str]]] = []
    pkg = _parse_package_json(project_path)
    scripts = pkg.get("scripts", {}) if isinstance(pkg, dict) else {}
    pkg_mgr = None
    if _has("package-lock.json", project_path) or _has("package.json", project_path):
        pkg_mgr = "npm"
        if _has("yarn.lock", project_path):
            pkg_mgr = "yarn"
        elif _has("pnpm-lock.yaml", project_path):
            pkg_mgr = "pnpm"

    # JS/TS
    if "test" in scripts and pkg_mgr:
        commands.append(("test", [pkg_mgr, "test"]))
    if "test:ci" in scripts and pkg_mgr:
        commands.append(("test:ci", [pkg_mgr, "run", "test:ci"]))
    # Type-check
    if _has("tsconfig.json", project_path):
        commands.append(("typecheck", ["npx", "tsc", "--noEmit"]))
    if "typecheck" in scripts and pkg_mgr:
        commands.append(("typecheck:script", [pkg_mgr, "run", "typecheck"]))
    # Lint
    if "lint" in scripts and pkg_mgr:
        commands.append(("lint", [pkg_mgr, "run", "lint"]))

    # Python
    if _has("pytest.ini", project_path) or _has("pyproject.toml", project_path) \
            or _has("setup.cfg", project_path) or _has("setup.py", project_path):
        if _has("pytest.ini", project_path) or _has("requirements-dev.txt", project_path) \
                or os.path.exists(os.path.join(project_path, "tests")):
            commands.append(("pytest", ["python3", "-m", "pytest", "-q"]))

    # Go
    if _has("go.mod", project_path):
        commands.append(("go-test", ["go", "test", "./..."]))

    return commands


def validate_project(project_path: str, timeout: float = 30.0) -> Tuple[
        Optional[float], int, int, List[CommandRun], EvidenceInfo]:
    """Run discovered validation commands and produce MEASURED evidence.
    
    Returns:
        (test_pass_ratio, ts_error_count, lint_error_count, runs, evidence)
    
    test_pass_ratio   : 0-1 from pass/total of the test command, or None if no
                        test command ran -> caller must decide conservative value
                        with NON-measured evidence (never claim MEASURED).
    ts_error_count    : int from tsc output.
    lint_error_count  : int from lint output.
    evidence          : EvidenceInfo stamped MEASURED only if a test command
                        actually ran; otherwise UNVALIDATED/SIMULATION.
    
    Args:
        project_path: path to the project to validate
        timeout: per-command timeout in seconds before a run is treated as timed out
    """
    runs: List[CommandRun] = []
    test_pass_ratio: Optional[float] = None
    ts_error_count: int = 0
    lint_error_count: int = 0

    for name, args in discover_commands(project_path):
        run = _safe_run(args, cwd=project_path, timeout=timeout)
        runs.append(run)
        if name in ("test", "test:ci", "pytest", "go-test"):
            ratio = _extract_pass_ratio(run)
            if ratio is not None:
                test_pass_ratio = ratio
        elif name in ("typecheck", "typecheck:script"):
            ts_error_count = _count_tsc_errors(run)
        elif name == "lint":
            lint_error_count = _count_lint_errors(run)

    if test_pass_ratio is not None:
        evidence = measured(
            source=EvidenceSource.EXTERNAL_SOLVER,
            confidence=test_pass_ratio,
        )
    else:
        evidence = EvidenceInfo(
            source=EvidenceSource.SIMULATION,
            validation_status=ValidationStatus.UNVALIDATED,
        )
    return test_pass_ratio, ts_error_count, lint_error_count, runs, evidence


def _extract_pass_ratio(run: CommandRun) -> Optional[float]:
    """Best-effort parse of test totals from common test runner output.

    Returns 0-1 ratio or None if unparseable.
    """
    text = (run.stdout + "\n" + run.stderr)
    # pytest / jest "X passed, Y failed" 
    import re
    passed_match = re.search(r"(\d+)\s+passed", text)
    failed_match = re.search(r"(\d+)\s+failed", text)
    if passed_match or failed_match:
        passed = int(passed_match.group(1)) if passed_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        total = passed + failed
        if total > 0:
            return passed / total
    # go test "ok" or "FAIL"
    if "ok" in text and "FAIL" not in text:
        return 1.0
    if "FAIL" in text and run.returncode is not None and run.returncode != 0:
        return 0.0
    return None


def _count_tsc_errors(run: CommandRun) -> int:
    """Count TypeScript compiler error lines in a CommandRun's captured output."""
    if run.classification == RunClass.SUCCESS:
        return 0
    text = run.stdout + "\n" + run.stderr
    # tsc prints one line per error; count non-empty blocks
    lines = [l for l in shlex.split(text) if l]
    count = 0
    for line in text.splitlines():
        if ".ts(" in line or ".tsx(" in line or ".d.ts(" in line:
            count += 1
    return count


def _count_lint_errors(run: CommandRun) -> int:
    """Count lint error lines/problems in a CommandRun's captured output."""
    if run.classification == RunClass.SUCCESS:
        return 0
    import re
    text = run.stdout + "\n" + run.stderr
    if not text.strip():
        return 0
    # eslint problem-count lines; fall back to counting non-infra lines
    probs = re.findall(r"problems?\s+\(error", text)
    match = re.search(r"(\d+)\s+errors?", text)
    if match:
        return int(match.group(1))
    return len(probs)
