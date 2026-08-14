"""
DevDomainAdapter — Maps codebase state into TELOS's World model.

Allows TELOS to reason about a software project:
  - Perceive: package.json, tsconfig, file counts, test coverage
  - Simulate: "what if we fix this dependency?" or "add tests?"
  - Evaluate: code quality score, dependency health, test coverage
  - Council: detect stale deps, missing tests, security issues

Usage:
    from telos.adapters.dev_domain_adapter import DevDomainSim, DevDomainAdpt
    sim = DevDomainSim("/path/to/project")
    pipeline = TelosV14Pipeline(PipelineConfig(simulator=sim, adapter=DevDomainAdpt()))
    result = pipeline.execute(sim.snapshot())
"""

import os
import json
import re
import subprocess
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter, EvaluationReport
from telos.world.facts import DomainFacts
from telos.world.world import World
from telos.intent_ir import IntentIR

# Feature dimensions for the state vector
# [0]: dep_count (total dependencies)
# [1]: dep_outdated_ratio (0-1, fraction of outdated deps)
# [2]: test_count
# [3]: test_pass_ratio (0-1)
# [4]: ts_error_count (0-1 scaled, capped at 100)
# [5]: lint_error_count (0-1 scaled)
# [6]: file_count_scaled (0-1, capped at 1000)
# [7]: bundle_size_mb_scaled (0-1, capped at 50MB)
# [8]: has_readme (0 or 1)
# [9]: has_ci_config (0 or 1)
# [10]: missing_peer_deps (0-1 scaled)

STATE_DIM = 11
# Perfect project state (all green)
GOAL_STATE = np.array([1.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.5, 0.2, 1.0, 1.0, 0.0])


@dataclass
class CodebaseSnapshot:
    """A snapshot of codebase health metrics."""
    dep_count: int = 0
    dep_outdated_count: int = 0
    test_count: int = 0
    test_pass_ratio: float = 1.0
    ts_error_count: int = 0
    lint_error_count: int = 0
    file_count: int = 0
    bundle_size_mb: float = 0.0
    has_readme: bool = False
    has_ci_config: bool = False
    missing_peer_deps: int = 0
    findings: List[str] = None

    def __post_init__(self):
        if self.findings is None:
            self.findings = []

    def to_vector(self) -> np.ndarray:
        return np.array([
            min(self.dep_count / 50, 1.0),
            min(self.dep_outdated_count / max(self.dep_count, 1), 1.0) if self.dep_count > 0 else 0.0,
            min(self.test_count / 100, 1.0),
            self.test_pass_ratio,
            min(self.ts_error_count / 100, 1.0),
            min(self.lint_error_count / 100, 1.0),
            min(self.file_count / 1000, 1.0),
            min(self.bundle_size_mb / 50, 1.0),
            1.0 if self.has_readme else 0.0,
            1.0 if self.has_ci_config else 0.0,
            min(self.missing_peer_deps / 10, 1.0),
        ], dtype=float)

def _scan_package_json(project_path: str) -> Tuple[int, int, int, List[str]]:
    """Scan package.json for dependency issues.

    Args:
        project_path: absolute path to the scanned project root.

    Returns:
        (dep_count, outdated_count, peer_mismatch_count, findings)
    """
    pkg_path = os.path.join(project_path, 'package.json')
    if not os.path.exists(pkg_path):
        return 0, 0, 0, []

    findings = []
    with open(pkg_path) as f:
        pkg = json.load(f)

    deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
    dep_count = len(deps)

    # Check for peer dependency issues (simple heuristic: look for "expo" deps not matching)
    missing_peer = 0
    has_expo = any('expo' in k for k in deps)
    has_expo_font = 'expo-font' in deps
    if has_expo and not has_expo_font:
        missing_peer += 1
        findings.append("⚠️  Missing expo-font (peer dep of @expo/vector-icons)")

    # Check for outdated patterns
    outdated = 0
    for name, version in deps.items():
        if version.startswith('^') or version.startswith('~'):
            outdated += 1  # lenient version ranges

    return dep_count, outdated, missing_peer, findings


def _scan_ts_config(project_path: str) -> Tuple[int, List[str]]:
    """Scan tsconfig for strict mode and errors.

    Args:
        project_path: absolute path to the scanned project root.

    Returns:
        (ts_error_count, findings)
    """
    ts_path = os.path.join(project_path, 'tsconfig.json')
    findings = []
    if not os.path.exists(ts_path):
        return 0, ["❌ No tsconfig.json found"]
    try:
        with open(ts_path) as f:
            ts = json.load(f)
        compiler = ts.get('compilerOptions', {})
        if not compiler.get('strict'):
            findings.append("⚠️  TypeScript strict mode not enabled")
        return 0, findings
    except json.JSONDecodeError:
        return 1, ["❌ tsconfig.json has invalid JSON"]


def _scan_file_tree(project_path: str) -> Tuple[int, bool, bool, List[str]]:
    """Count files and check for README/CI config.

    Args:
        project_path: absolute path to the scanned project root.

    Returns:
        (file_count, has_docs, has_tests, findings)
    """
    file_count = 0
    has_readme = False
    has_ci = False
    test_files = 0
    findings = []

    for root, dirs, files in os.walk(project_path):
        # Skip node_modules and build dirs
        if 'node_modules' in root or '.git' in root or 'dist' in root or 'build' in root:
            continue
        for f in files:
            file_count += 1
            if f.lower() == 'readme.md':
                has_readme = True
            if f in ('.github', '.gitlab-ci.yml', 'Dockerfile', '.drone.yml'):
                has_ci = True
            if f.endswith('.test.ts') or f.endswith('.test.tsx') or f.endswith('.spec.ts') or f.endswith('_test.go'):
                test_files += 1

    if not has_readme:
        findings.append("📄 No README.md found")
    if not has_ci:
        findings.append("🔧 No CI config detected")

    return file_count, has_readme, has_ci, test_files, findings


def _check_lint_errors(project_path: str) -> int:
    """Try running linter to count errors (non-blocking).

    Args:
        project_path: absolute path to the scanned project root.

    Returns:
        Lint error count.
    """
    try:
        result = subprocess.run(
            ['npx', 'eslint', '--format', 'json', 'src/', '--max-warnings', '0'],
            cwd=project_path, capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0 and result.stdout:
            try:
                data = json.loads(result.stdout)
                return sum(len(f.get('messages', [])) for f in data)
            except json.JSONDecodeError:
                pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return 0


class DevDomainSim(DomainSimulator):
    """Simulates a codebase as TELOS domain.

    Takes a project path and provides:
      - legal_transitions: what actions TELOS can propose
      - simulate: what-if scenarios for code improvements
      - evaluate: score the quality of the codebase
    """

    def __init__(self, project_path: str, seed=None):
        self.project_path = project_path
        # Pattern: one RNG authority per engine — private RandomState,
        # never global np.random in the simulation hot path.
        self._rng = np.random.RandomState(seed)
        self._last_snapshot: Optional[CodebaseSnapshot] = None

    def initialize(self) -> None:
        pass

    def cleanup(self) -> None:
        pass

    def snapshot(self) -> np.ndarray:
        """Take a fresh snapshot of the codebase and return as state vector."""
        deps, outdated, missing_peer, dep_findings = _scan_package_json(self.project_path)
        ts_errors, ts_findings = _scan_ts_config(self.project_path)
        files, has_readme, has_ci, test_files, file_findings = _scan_file_tree(self.project_path)
        lint_errors = _check_lint_errors(self.project_path)

        findings = dep_findings + ts_findings + file_findings
        bundle_mb = 0.0
        node_mods = os.path.join(self.project_path, 'node_modules')
        if os.path.exists(node_mods):
            try:
                result = subprocess.run(['du', '-sk', node_mods], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    bundle_mb = int(result.stdout.split()[0]) / 1024
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        self._last_snapshot = CodebaseSnapshot(
            dep_count=deps,
            dep_outdated_count=outdated,
            test_count=test_files,
            test_pass_ratio=1.0,  # assume pass unless we run tests
            ts_error_count=ts_errors,
            lint_error_count=lint_errors,
            file_count=files,
            bundle_size_mb=bundle_mb,
            has_readme=has_readme,
            has_ci_config=has_ci,
            missing_peer_deps=missing_peer,
            findings=findings,
        )

        return self._last_snapshot.to_vector()

    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        """Possible actions TELOS can suggest for a codebase.

        Args:
            state: current dev-domain state vector.

        Returns:
            List of candidate action vectors.
        """
        return [
            np.array([0, 0, 0.1, 0, 0, 0, 0, 0, 0, 0, 0]),  # add tests
            np.array([0, -0.1, 0, 0, 0, 0, 0, 0, 0, 0, 0]),  # fix deps
            np.array([0, 0, 0, 0, -0.1, 0, 0, 0, 0, 0, 0]),  # fix TS errors
            np.array([0, 0, 0, 0, 0, -0.1, 0, 0, 0, 0, 0]),  # fix lint errors
            np.array([0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0]),    # add README
            np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0]),    # add CI
            np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -0.1]), # fix peer deps
        ]

    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        return np.clip(state + action, 0.0, 1.0)

    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        futures = []
        s = state.copy()
        for _ in range(horizon):
            actions = self.legal_transitions(s)
            chosen = actions[int(self._rng.randint(len(actions)))]
            s = self.transition(s, chosen)
            futures.append(World(state=s.copy(), metadata={"simulated": True}))
        return futures

    def get_facts(self, state: np.ndarray) -> DomainFacts:
        findings = self._last_snapshot.findings if self._last_snapshot else []
        return DomainFacts(
            state=state.copy(),
            resources={
                "dep_health": float(1.0 - state[1]),
                "test_coverage": float(state[2]),
                "ts_health": float(1.0 - state[4]),
            },
            constraints=[],
            events=findings[:3],
            metrics={
                "code_quality": float(1.0 - (state[4] + state[5] + state[1]) / 3),
                "test_health": float(state[3]),
                "doc_health": float(state[8]),
            },
            metadata={"project_path": self.project_path},
        )

    def terminal(self, state: np.ndarray) -> bool:
        return bool(np.linalg.norm(GOAL_STATE - state[:STATE_DIM]) < 0.3)

    def evaluate(self, state: np.ndarray) -> EvaluationReport:
        dist = np.linalg.norm(GOAL_STATE - state[:STATE_DIM])
        return EvaluationReport(
            objectives={
                "code_quality": float(1.0 - dist / STATE_DIM),
                "dep_health": float(1.0 - state[1]),
                "ts_health": float(1.0 - state[4]),
            },
            risks=float(state[4] + state[5]),  # risk from TS + lint errors
        )


class DevDomainAdpt(DomainAdapter):
    """Converts TELOS intents into developer actions."""

    def forward(self, x: Any) -> Any:
        return x

    def inverse(self, x: Any) -> Any:
        return x

    def intent_to_action(self, intent: IntentIR, state: np.ndarray,
                          mission_dir: np.ndarray) -> np.ndarray:
        if "action_vector" in intent.params:
            return np.asarray(intent.params["action_vector"], dtype=float)
        diff = GOAL_STATE[:len(state)] - state
        rng = getattr(self, '_rng', None) or np.random.RandomState()
        return np.sign(diff + rng.randn(len(state)) * 0.1).astype(float) * 0.1

    @property
    def name(self) -> str:
        return "devdomain"
