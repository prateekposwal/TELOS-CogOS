"""
RepoEvidenceValidator — council advisor that GENUINELY READS raw repo evidence.

PATTERN (real perception): raw artifacts reach the council as evidence, never
hidden behind a vector. This validator reads `domain_facts.metadata["repo_snapshot"]`
— the RepoSnapshot dict carrying unified diff text, failing test names, and
traceback frames actually produced by real git commands — and quotes THE RAW
TEXT in its signal reasons. A validator that only saw the numeric vector could
never name the failing test; this one can.

Blocking rules (evidence-anchored, Lambda 2.3):
  1. Tests are failing AND the diff touches one of the failing test files or
     the module under test -> dissent, quoting the failing test ids.
  2. A traceback's exception line names a file that the diff changes -> dissent,
     quoting the raw exception line and the file.
  3. A huge uncommitted diff with zero test evidence -> advisory only (pass
     with warning): uncommitted work is not by itself a safety violation.
  4. No repo snapshot present -> abstain (pass, zero weight). This validator
     never penalises non-git-repo domains.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from telos.core.council.base import Validator, ValidationSignal
from telos.world.world import World
from telos.intent_ir import IntentIR

# Advisory thresholds on raw evidence (measured, not invented).
LARGE_DIFF_LINES = 800      # above this, an advisory warning fires
MAX_QUOTED_TESTS = 5        # cap on test ids quoted in a reason string
TRACEBACK_QUOTE = 3         # max traceback frames quoted in metadata


class RepoEvidenceValidator(Validator):
    """Reads the raw RepoSnapshot artifacts and reports evidence-anchored dissent."""

    @property
    def name(self) -> str:
        return "RepoEvidenceValidator"

    def _snapshot_dict(self, domain_facts: Any) -> Optional[Dict[str, Any]]:
        """Extract the RepoSnapshot dict from domain facts, if present.

        Args:
            domain_facts: optional DomainFacts for the current cycle.

        Returns:
            The repo_snapshot dict, or None when this domain carries none.
        """
        if domain_facts is None:
            return None
        metadata = getattr(domain_facts, "metadata", None) or {}
        snap = metadata.get("repo_snapshot")
        if isinstance(snap, dict):
            return snap
        return None

    def _changed_paths(self, snap: Dict[str, Any]) -> List[str]:
        """Changed file paths from the snapshot's changed_files channel.

        Args:
            snap: the RepoSnapshot dict.

        Returns:
            List of changed file paths (raw path text from git status).
        """
        paths: List[str] = []
        for entry in snap.get("changed_files", []) or []:
            path = entry.get("path") if isinstance(entry, dict) else None
            if path and path not in paths:
                paths.append(path)
        return paths

    @staticmethod
    def _probes_from_line(line: str) -> List[str]:
        """Extract file/module probe tokens from a raw traceback line.

        Args:
            line: a raw frame ('  File "/x/tests/test_loader.py"...') or an
                exception line ("ModuleNotFoundError: No module named 'src.loader'").

        Returns:
            Probe tokens (paths, basenames, normalized module names).
        """
        probes: List[str] = []
        fm = re.search(r'File "([^"]+)"', line)
        if fm:
            probes.append(fm.group(1))
            probes.append(fm.group(1).split("/")[-1].split("\\")[-1])
        qm = re.findall(r"'([A-Za-z_][A-Za-z0-9_.]*)'", line)
        for m in qm:
            normalized = m.replace(".", "/")
            probes.append(normalized)
            probes.append(normalized.split("/")[-1])
        return [p for p in probes if p]

    def _diff_touches(self, paths: List[str], probes: List[str]) -> bool:
        """True when any probe token (test id / file path / module) hits a changed path.

        Args:
            paths: changed file paths from the snapshot.
            probes: raw tokens to search for inside the changed paths.

        Returns:
            True if any changed path contains a probe (or vice versa).
        """
        for p in paths:
            for probe in probes:
                if probe and (probe in p or p in probe):
                    return True
        return False

    def validate(self, world: World, intent: Optional[IntentIR],
                 domain_facts: Optional[Any] = None) -> ValidationSignal:
        snap = self._snapshot_dict(domain_facts)
        if snap is None:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.0,
                reason="no repo snapshot in domain facts — abstaining",
                evidence_weight=0.0,
            )

        changed = self._changed_paths(snap)
        failing: List[str] = list(snap.get("failing_test_names", []) or [])
        tracebacks: List[str] = list(snap.get("traceback_frames", []) or [])
        diff_text: str = snap.get("diff_text", "") or ""
        added = int(snap.get("added_lines", 0) or 0)
        removed = int(snap.get("removed_lines", 0) or 0)
        findings: List[str] = list(snap.get("findings", []) or [])
        provenance: Dict[str, str] = snap.get("evidence_provenance", {}) or {}
        # test_measured means TEST evidence was actually measured — not merely
        # that some git channel responded (Lambda 2.3: no conflation).
        test_measured = provenance.get("test_output", "").startswith("measured")
        any_measured = any(v.startswith("measured") for v in provenance.values())

        issues: List[str] = []

        # Rule 1: failing tests whose ids overlap the changed files (raw text).
        touching_failures: List[str] = []
        for test_id in failing:
            if self._diff_touches(changed, [test_id]):
                touching_failures.append(test_id)
        if touching_failures:
            quoted = ", ".join(touching_failures[:MAX_QUOTED_TESTS])
            issues.append(
                f"failing test(s) touch changed files: {quoted} "
                f"(raw evidence, n={len(touching_failures)})"
            )
        elif failing:
            quoted = ", ".join(failing[:MAX_QUOTED_TESTS])
            issues.append(
                f"test suite failing but outside changed files: {quoted} "
                f"(raw evidence, n={len(failing)})"
            )

        # Rule 2: traceback frames naming files the diff changes.
        for frame in tracebacks:
            line = frame.strip()
            if not line:
                continue
            probes = self._probes_from_line(line)
            if self._diff_touches(changed, probes):
                file_hit = next(
                    (p for p in changed
                     for pr in probes if pr and (pr in p or p in pr)),
                    probes[0] if probes else "?",
                )
                issues.append(
                    f"traceback frame names changed file '{file_hit}': {line}"
                )
                break

        # Rule 3: advisory on huge uncommitted diff with no test evidence.
        if not issues and (added + removed) >= LARGE_DIFF_LINES and not test_measured:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.3,
                reason=(
                    f"uncommitted diff of +{added}/-{removed} lines with NO "
                    f"test evidence measured (advisory: validate before act); "
                    f"findings: {' | '.join(findings[:2])}"
                ),
                evidence_weight=0.2,
                metadata={"diff_added": added, "diff_removed": removed,
                          "test_measured": False, "any_git_measured": any_measured},
            )

        if issues:
            evidence_weight = min(
                1.0,
                0.4 + 0.2 * len(issues) + min(len(failing) * 0.1, 0.3),
            )
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=-0.8,
                reason=" | ".join(issues),
                evidence_weight=evidence_weight,
                metadata={
                    "failing_tests": failing[:MAX_QUOTED_TESTS],
                    "changed_files": changed[:10],
                    "traceback_frames": tracebacks[:TRACEBACK_QUOTE],
                    "diff_bytes": len(diff_text),
                    "test_measured": test_measured,
                },
            )

        # Clean-but-measured: pass with real confidence.
        if test_measured:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.7,
                reason=(
                    f"repo evidence read: {len(changed)} changed files, "
                    f"{len(failing)} failing tests, {len(tracebacks)} "
                    f"traceback frames — nothing contradicting the intent"
                ),
                evidence_weight=0.3,
                metadata={"test_measured": True, "changed_count": len(changed)},
            )

        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=0.4,
            reason=(
                f"repo snapshot read with {len(findings)} finding(s): "
                f"{' | '.join(findings[:2]) or 'no findings'}"
            ),
            evidence_weight=0.2,
            metadata={"changed_count": len(changed), "test_measured": False},
        )


__all__ = ["RepoEvidenceValidator", "TRACEBACK_QUOTE"]
