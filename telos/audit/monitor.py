"""
System Transparency Monitor — Empirical Proof of Latent Cognition

The Monitor captures what the Cognitive Streams were doing "under
the hood" during each decision cycle. While the user interacts only
with the final action, the audit log records exactly which latent
processes were activated, what they contributed, and how resources
were allocated across them.

This is the empirical proof of the Principle of Latent Cognition:
invisible coordination → visible coherent action.

Council metrics (DI, MD, blocking validators) are reported as
quantitative evidence of Epistemic Integrity.
"""

import json
import os
import time
import logging
from typing import List, Optional, Dict
from dataclasses import dataclass, field

from telos.core.runtime import DecisionTrace

logger = logging.getLogger('telos_monitor')


@dataclass
class MonitorConfig:
    output_dir: str = "telos/audit/runtime"
    log_filename: str = "decision_log.json"
    report_filename: str = "transparency_report.md"
    max_entries: int = 500
    auto_flush: bool = True


class TransparencyMonitor:
    """Captures and persists the latent cognition audit trail.

    After each Pipeline.execute(), call monitor.record(trace) to
    capture the DecisionTrace. The monitor writes structured JSON
    logs and generates human-readable transparency reports.

    Usage:
        monitor = TransparencyMonitor()
        result = pipeline.execute(state)
        monitor.record(result.decision_trace)
        report = monitor.generate_report()
    """

    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()
        self._traces: List[DecisionTrace] = []
        self._ensure_output_dir()

    def record(self, trace: DecisionTrace) -> None:
        """Capture a DecisionTrace from a single pipeline cycle."""
        self._traces.append(trace)

        if len(self._traces) > self.config.max_entries:
            self._traces = self._traces[-self.config.max_entries // 2:]

        if self.config.auto_flush:
            self._flush_json()

    def _flush_json(self) -> None:
        """Write all traces to the decision log JSON file."""
        filepath = os.path.join(self.config.output_dir, self.config.log_filename)
        data = {
            "version": "1.0",
            "total_cycles": len(self._traces),
            "traces": [t.to_dict() for t in self._traces],
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def generate_report(self, infra_stats: Optional[Dict] = None) -> str:
        """Generate a human-readable transparency report.

        The report demonstrates:
        1. Latent Cognition: stream activations, budget allocation, decision trace
        2. Epistemic Integrity: Council verdicts, DI, MD, blocking validators
        3. Infrastructure Health: calibrator, failures, policy, audit (if provided)
        Args:
            infra_stats: the infra_stats argument for this call.
        """
        if not self._traces:
            return "# Transparency Report\n\nNo decision cycles recorded."

        lines = [
            "# TELOS Transparency Report",
            f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Total Decision Cycles:** {len(self._traces)}",
            "",
            "## Principle of Latent Cognition",
            "",
            "> \"An intelligent system is defined not by the number of visible capabilities",
            "> it possesses, but by the invisible coordination of latent cognitive processes",
            "> working toward a unified mission.\"",
            "",
            "## Principle of Epistemic Integrity",
            "",
            "> \"An intelligent system is not defined by how confidently it pursues a mission,",
            "> but by its ability to continuously expose, evaluate, and integrate",
            "> inconvenient truths before acting.\"",
            "",
            "This report provides empirical evidence of both principles by exposing the",
            "internal stream activations, budget allocations, Council validations, and",
            "decision traces that produced each visible action.",
            "",
            "---",
            "",
        ]

        # Summary statistics
        total_activated = sum(
            len([a for a in t.stream_activations if a.activated])
            for t in self._traces
        )
        total_streams = sum(len(t.stream_activations) for t in self._traces)
        total_budget_used = sum(t.budget_consumed_ms for t in self._traces)
        avg_health = sum(t.health_score for t in self._traces) / len(self._traces)
        avg_di = sum(t.decision_integrity for t in self._traces) / len(self._traces)
        avg_md = sum(t.mission_drift for t in self._traces) / len(self._traces)
        blocked_cycles = sum(1 for t in self._traces if not t.council_validated)

        lines.extend([
            "## System Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Cycles | {len(self._traces)} |",
            f"| Stream Activations | {total_activated}/{total_streams} |",
            f"| Activation Rate | {total_activated/max(total_streams,1)*100:.1f}% |",
            f"| Total Budget Consumed | {total_budget_used:.1f}ms |",
            f"| Average Health | {avg_health:.3f} |",
            f"| Average Decision Integrity (DI) | {avg_di:.3f} |",
            f"| Average Mission Drift (MD) | {avg_md:.3f} |",
            f"| Council-Blocked Cycles | {blocked_cycles} |",
            "",
            "### Decision Integrity (DI)",
            "",
            "DI = 1 - sum(IgnoredEvidence × BeliefConfidence) / TotalAvailableEvidence",
            "",
            f"Average DI of {avg_di:.3f} means the system is "
            f"{'strongly evidence-led' if avg_di > 0.8 else 'sometimes ignoring evidence'} "
            f"across all cycles.",
            "",
            "### Mission Drift (MD)",
            "",
            "MD = ||PredictedState - ObservedState||",
            "",
            f"Average MD of {avg_md:.3f} means the system's world model is "
            f"{'well-calibrated' if avg_md < 3.0 else 'diverging from reality'}.",
            "",
            "---",
            "",
        ])

        # Infrastructure Health section (from InfraManager)
        if infra_stats:
            calibrator = infra_stats.get("calibrator", {})
            failures = infra_stats.get("failures", {})
            policy = infra_stats.get("policy", {})
            audit = infra_stats.get("audit", {})

            lines.extend([
                "## Infrastructure Health (Meta-Cognitive Layer)\n",
                "### Stream Calibrator",
                "",
                "| Stream | Accuracy | Reliability | Influence | Observations |",
                "|--------|----------|-------------|-----------|--------------|",
            ])
            cal_data = calibrator.get("calibrations", {})
            if cal_data:
                for name, c in cal_data.items():
                    lines.append(
                        f"| {name} | {c['accuracy']:.3f} | {c['reliability']:.3f} "
                        f"| {c['influence']:.3f} | {c['observations']} |"
                    )
            else:
                lines.append("| *No calibrations yet* | - | - | - | - |")
            lines.append("")

            failures_by_type = failures.get("by_type", {})
            total_fail = failures.get("total_failures", 0)
            root_causes = failures.get("root_causes", {})
            lines.extend([
                "### Failure Ledger (Kintsugi)",
                "",
                f"- **Total Failures:** {total_fail}",
                f"  - Council Blocks: {failures_by_type.get('council_block', 0)}",
                f"  - Firewall Blocks: {failures_by_type.get('firewall_block', 0)}",
                f"  - High Drift: {failures_by_type.get('high_drift', 0)}",
                f"  - Low Integrity: {failures_by_type.get('low_integrity', 0)}",
                "",
                "**Root Cause Distribution:**",
            ])
            for cause, count in root_causes.items():
                lines.append(f"  - {cause}: {count}")
            lines.append("")

            policy_info = policy
            lines.extend([
                "### Mission Policy",
                "",
                f"- **Mission:** `{policy_info.get('mission', 'default')}`",
                f"- **Risk Tolerance:** {policy_info.get('risk_tolerance', 0.0):.2f}",
                f"- **Exploration Budget:** {policy_info.get('exploration_budget', 0.0):.2f}",
                f"- **Ambition Level:** {policy_info.get('ambition_level', 0.0):.2f}",
                f"- **Firewall DI Threshold:** {policy_info.get('firewall_di_threshold', 0.0):.2f}",
                f"- **Policy Changes:** {policy_info.get('policy_changes', 0)}",
                "",
                "### Audit Controller (Health Trends)",
                "",
                f"- **Cycles Observed:** {audit.get('cycles_observed', 0)}",
                f"- **Failures:** {audit.get('failures', 0)}",
                f"- **Governance Blocks:** {audit.get('governance_blocks', 0)}",
                f"- **DI Trend (last 10):** {audit.get('di_trend', 0.0):.3f}",
                f"- **MD Trend (last 10):** {audit.get('md_trend', 0.0):.3f}",
                "",
                "---",
                "",
            ])

        # Per-cycle detail
        lines.append("## Decision Cycle Details\n")
        for trace in self._traces[-10:]:
            lines.extend(self._format_cycle_detail(trace))

        report = "\n".join(lines)

        report_path = os.path.join(self.config.output_dir, self.config.report_filename)
        with open(report_path, 'w') as f:
            f.write(report)

        logger.info(f"Transparency report written to {report_path}")
        return report

    def _format_cycle_detail(self, trace: DecisionTrace) -> List[str]:
        """Format a single decision cycle for the report.
            Args:
                trace: the decision trace for this cycle
        """
        council_badge = "✅ APPROVED" if trace.council_validated else "❌ BLOCKED"
        lines = [
            f"### Cycle {trace.cycle_id}",
            f"- **Duration:** {trace.cycle_duration_ms:.2f}ms",
            f"- **Budget:** {trace.budget_consumed_ms:.1f}/{trace.budget_total_ms:.1f}ms",
            f"- **Health:** {trace.health_score:.3f}",
            f"- **Representation:** {trace.representation}",
            f"- **Worlds Simulated:** {trace.worlds_simulated}",
            f"- **Council: {council_badge}**",
            f"- **DI:** {trace.decision_integrity:.3f}",
            f"- **MD:** {trace.mission_drift:.3f}",
            "",
        ]

        if trace.blocking_validator:
            lines.append(f"  ⛔ **Blocked by:** `{trace.blocking_validator}`\n")

        if trace.firewall_blocked:
            lines.append(f"  🔒 **Firewall Blocked:** `{trace.firewall_blocked_by}`\n")

        # Stream activations table
        lines.append("**Stream Activations (Latent Processes):**\n")
        lines.append("| Stream | Priority | Activated | Intent | Cost |")
        lines.append("|--------|----------|-----------|--------|------|")
        for sa in trace.stream_activations:
            status = "yes" if sa.activated else "SKIPPED"
            intent_type = sa.intent.intent_type if sa.intent else "-"
            lines.append(
                f"| {sa.stream_name} | {sa.priority:.1f} | {status} "
                f"| {intent_type} | {sa.cost_ms:.2f}ms |"
            )
        lines.append("")

        # Ω Vector (Inquiry Stream)
        if hasattr(trace, 'inquiry_omega_vector') and trace.inquiry_omega_vector is not None:
            ov = trace.inquiry_omega_vector
            if ov.get('world', 0) or ov.get('identity', 0) or ov.get('other', 0):
                lines.append("**Ω Vector (Inquiry Stream):**")
                lines.append("")
                lines.append("  - Ω_W (World): {:.3f}".format(ov.get('world', 0)))
                lines.append("  - Ω_I (Identity): {:.3f}".format(ov.get('identity', 0)))
                lines.append("  - Ω_O (Other): {:.3f}".format(ov.get('other', 0)))
                if trace.selected_question:
                    lines.append("  - Question: {}".format(trace.selected_question.get('question', str(trace.selected_question))))
                if trace.inquiry_omega_value:
                    lines.append("  - Ω Value: {:.3f}".format(trace.inquiry_omega_value))
                lines.append("")

        # Council signals table
        if trace.council_signals:
            lines.append("**Council of Cognitive Advisors (Epistemic Integrity):**\n")
            lines.append("| Validator | Passed | Confidence | Reason | Evidence |")
            lines.append("|-----------|--------|------------|--------|----------|")
            for sig in trace.council_signals:
                badge = "✅" if sig["passed"] else "❌"
                lines.append(
                    f"| {sig['validator']} | {badge} | {sig['confidence']:+.2f} "
                    f"| {sig['reason']} | {sig['evidence_weight']:.2f} |"
                )
            lines.append("")

        # Governance signals table
        if trace.governance_signals:
            lines.append("**Governance (Cognitive Confidentiality):**\n")
            lines.append("| Check | Passed | Reason |")
            lines.append("|-------|--------|--------|")
            for sig in trace.governance_signals:
                badge = "✅" if sig.get("passed", False) else "❌"
                lines.append(
                    f"| {sig.get('check', '?')} | {badge} "
                    f"| {sig.get('reason', '-')} |"
                )
            lines.append("")

        # Semantic Depth (Cognitive Identity)
        if trace.semantic_depths:
            lines.append("**Semantic Depth (Cognitive Identity):**\n")
            lines.append("| Entity | Observable | Historical | Mission | Identity |")
            lines.append("|--------|------------|------------|---------|----------|")
            for sd in trace.semantic_depths:
                lines.append(
                    f"| `{sd.get('entity_id', '?')[:8]}` "
                    f"| norm={sd.get('observable_state', {}).get('state_norm', 0):.1f} "
                    f"| {sd.get('historical_context', '-')} "
                    f"| {sd.get('mission_context', '-')} "
                    f"| `{sd.get('semantic_identity', '-')}` |"
                )
            lines.append("")

        # Strategic options (Axiom 4.3 — Possibility Preservation)
        if hasattr(trace, 'strategic_options') and trace.strategic_options:
            lines.append("**Strategic Options (Alternative Futures):**\n")
            for opt in trace.strategic_options[:5]:
                lines.append(
                    f"  - Rank #{opt['rank']}: score={opt['score']:.4f}, "
                    f"horizon={opt['horizon']}"
                )
            if len(trace.strategic_options) > 5:
                lines.append(f"  - ... and {len(trace.strategic_options) - 5} more")
            lines.append("")

        # Decision trace
        if trace.selected_intent:
            lines.extend([
                "**Decision Trace:**",
                f"- Intent: `{trace.selected_intent.intent_type}`",
                f"- Confidence: {trace.selected_intent.confidence:.3f}",
            ])
            if trace.selected_action is not None:
                lines.append(f"- Action: `{trace.selected_action.tolist()}`")
            lines.append("")

        # Domain facts summary
        if trace.domain_facts:
            facts = trace.domain_facts
            if facts.constraints:
                lines.append(f"- Constraints: {', '.join(facts.constraints[:3])}")
            if facts.events:
                lines.append(f"- Events: {', '.join(facts.events[:3])}")
            lines.append("")

        lines.append("---\n")
        return lines

    def _ensure_output_dir(self) -> None:
        os.makedirs(self.config.output_dir, exist_ok=True)

    def get_traces(self) -> List[DecisionTrace]:
        return list(self._traces)

    def clear(self) -> None:
        self._traces.clear()
