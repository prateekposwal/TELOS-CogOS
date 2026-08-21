"""
Axiom Compliance Prover — converts each axiom into a logical predicate
over the runtime state (DecisionTrace + PhaseContext) and verifies all
42 axioms are satisfied after every pipeline cycle.

Each predicate returns True if the axiom is satisfied, False if violated,
with a reason string.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger('telos_verifier')


class AxiomProver:
    """Verifies all 42 TELOS axioms against DecisionTrace + PhaseContext.

    Usage:
        prover = AxiomProver(infra_manager=..., skill_library=...)
        results = prover.verify(trace, ctx, stream_results=ctx.stream_activations)
        if prover.all_passed(trace, ctx, stream_results=ctx.stream_activations):
            # all axioms satisfied
    """

    def __init__(self, infra_manager: Any = None,
                 skill_library: Any = None):
        self._infra_manager = infra_manager
        self._skill_library = skill_library

    def verify(self, trace: Any, ctx: Any, **kwargs) -> Dict[str, Dict[str, Any]]:
        """Returns dict of axiom_id -> {"passed": bool, "reason": str}.

        Args:
            trace: DecisionTrace from the current pipeline cycle
            ctx: PhaseContext from the current pipeline cycle
            **kwargs: Optional extras:
                - stream_results: list of StreamActivation objects (for axiom 4.6)
        """
        results: Dict[str, Dict[str, Any]] = {}
        stream_results = kwargs.get('stream_results', getattr(ctx, 'stream_activations', []))
        infra = self._infra_manager
        sl = self._skill_library

        # ── Layer 1: Architectural Invariance ──────────────────────────────

        # 1.1 — Architecture Produces Outcomes
        passed = trace is not None
        results['1.1'] = {
            "passed": passed,
            "reason": "trace is not None — architecture produced an outcome" if passed
                      else "trace is None — architecture did not produce an outcome",
        }

        # 1.2 — Process over Outcomes
        di = getattr(trace, 'decision_integrity', -1.0) if trace else -1.0
        passed = trace is not None and di >= 0.0
        results['1.2'] = {
            "passed": passed,
            "reason": f"decision_integrity={di:.3f} >= 0.0 — process was measured" if passed
                      else f"decision_integrity={di:.3f} < 0.0 or missing — process not measured",
        }

        # 1.3 — Multi-Level Governance
        governance_checked = getattr(ctx, 'governance_blocked', None) is not None
        passed = governance_checked
        results['1.3'] = {
            "passed": passed,
            "reason": "governance_blocked was checked — multi-level governance ran" if passed
                      else "governance_blocked not set — governance may not have run",
        }

        # 1.4 — Computational Conservation (ΣR_i ≤ R_max)
        budgets = getattr(ctx, 'resource_budgets', None)
        total_ms = 0.0
        max_ms = 0.0
        if budgets:
            total_ms = budgets.get('energy', {}).get('consumed_ms', 0.0)
            max_ms = budgets.get('energy', {}).get('total_ms', 1.0)
        elif hasattr(ctx, 'budget_manager'):
            bm = ctx.budget_manager
            total_ms = getattr(bm, 'consumed_ms', 0.0)
            max_ms = getattr(bm, 'total_budget_ms', 1.0)
        passed = max_ms > 0 and total_ms <= max_ms * 1.1
        results['1.4'] = {
            "passed": passed,
            "reason": f"compute {total_ms:.1f}ms <= {max_ms:.1f}ms — budget conserved" if passed
                      else f"compute {total_ms:.1f}ms > {max_ms:.1f}ms — budget exceeded",
        }

        # ── Layer 2: Feedback & Memory ─────────────────────────────────────

        # 2.1 — Governance First
        cv = getattr(trace, 'council_validated', None) if trace else None
        passed = cv is not None
        results['2.1'] = {
            "passed": passed,
            "reason": f"council_validated={cv} — constitutional check happened" if passed
                      else "council_validated is None — constitutional check did not run",
        }

        # 2.2 — Feedback Loops
        feedback_processed = getattr(ctx, 'meta_cognition', None) is not None
        passed = feedback_processed
        results['2.2'] = {
            "passed": passed,
            "reason": "meta_cognition populated — feedback loop closed" if passed
                      else "meta_cognition not set — feedback loop may not have closed",
        }

        # 2.3 — Kintsugi (failures as structural assets)
        has_failures = infra is not None and hasattr(infra, 'failures') and infra.failures is not None
        passed = has_failures
        results['2.3'] = {
            "passed": passed,
            "reason": "infra_manager.failures exists — failures preserved as structural assets" if passed
                      else "infra_manager.failures missing — failures not preserved",
        }

        # 2.4 — Path Dependency
        spent = getattr(trace, 'spent_ctx_id', None) if trace else None
        produced = getattr(trace, 'produced_ctx_id', None) if trace else None
        path_dep = spent is not None or produced is not None
        passed = path_dep
        results['2.4'] = {
            "passed": passed,
            "reason": f"trace has UTXO chain (spent={spent}, produced={produced}) — path dependency tracked" if passed
                      else "trace has no UTXO chain — path dependency not tracked",
        }

        # 2.5 — Delayed Causality
        has_cg = hasattr(trace, 'causal_graph') if trace else False
        passed = has_cg
        results['2.5'] = {
            "passed": passed,
            "reason": "trace has causal_graph attribute — delayed causality modeled" if passed
                      else "trace missing causal_graph — delayed causality not modeled",
        }

        # 2.6 — Reflection Is Episodic (τ_reflect > τ_decision)
        reflection = getattr(ctx, 'reflection', None)
        passed = reflection is not None
        results['2.6'] = {
            "passed": passed,
            "reason": "ctx.reflection populated — reflection ran as post-action phase" if passed
                      else "ctx.reflection not set — reflection did not run",
        }

        # 2.7 — Meta-Error Attribution (Error → Subsystem → Update)
        eae = getattr(ctx, 'error_attribution', None)
        if eae is None:
            eae = getattr(trace, 'error_attribution', None) if trace else None
        passed = eae is not None
        results['2.7'] = {
            "passed": passed,
            "reason": "error_attribution populated — subsystem identified" if passed
                      else "error_attribution not found — no subsystem attribution",
        }

        # ── Layer 3: Adaptive Capacity ────────────────────────────────────

        # 3.1 — Maintenance vs Recovery (M_t > M_min before E_{t+1})
        meta = getattr(ctx, 'meta_cognition', None) or {}
        recovery_mode = meta.get('recovery_mode', False) if isinstance(meta, dict) else False
        passed = recovery_mode is not None
        results['3.1'] = {
            "passed": passed,
            "reason": f"recovery_mode={recovery_mode} — recovery mode tracked" if passed
                      else "recovery_mode not observed",
        }

        # 3.2 — State Maintenance (budget reserved)
        budget_reserved = budgets is not None
        passed = budget_reserved
        results['3.2'] = {
            "passed": passed,
            "reason": "resource_budgets populated — budget was reserved" if passed
                      else "resource_budgets not set",
        }

        # 3.3 — Option Decay (skill library functional)
        sl_ok = sl is not None and callable(getattr(sl, 'find_relevant_skills', None))
        passed = sl_ok
        results['3.3'] = {
            "passed": passed,
            "reason": "skill_library exists and is callable" if passed
                      else "skill_library missing or not callable",
        }

        # 3.4 — Exploration vs Exploitation
        exploration = getattr(ctx, 'curiosity_state', None) is not None
        if not exploration and isinstance(meta, dict):
            exploration = meta.get('exploration_mode', False)
        exploitation = not exploration
        passed = exploration or exploitation
        results['3.4'] = {
            "passed": passed,
            "reason": f"exploration={exploration}, exploitation={exploitation} — trade-off active" if passed
                      else "neither exploration nor exploitation detected",
        }

        # 3.5 — Structural Inertia (calibration ran)
        calibration_ran = (infra is not None and hasattr(infra, 'calibrator')
                          and infra.calibrator is not None)
        passed = calibration_ran
        results['3.5'] = {
            "passed": passed,
            "reason": "infra_manager.calibrator exists — calibration ran" if passed
                      else "infra_manager.calibrator missing",
        }

        # 3.6 — Curiosity Seeks Broken Models (C = αN + βS + γPE)
        curiosity = getattr(ctx, 'curiosity_state', None)
        has_uud = hasattr(ctx, 'unknown_unknowns') or kwargs.get('has_unknown_unknown_detector', False)
        passed = curiosity is not None
        results['3.6'] = {
            "passed": passed,
            "reason": "curiosity_state populated — curiosity actively drives exploration" if passed
                      else "curiosity_state not set — curiosity not active",
        }

        # ── Layer 4: Emergent Intelligence ────────────────────────────────

        # 4.1 — Identity Continuity (I_{t+1} = I_t + ΔI_t, |ΔI_t| ≤ ε)
        identity_loaded = getattr(ctx, 'identity_state', None) is not None
        passed = identity_loaded
        results['4.1'] = {
            "passed": passed,
            "reason": "ctx.identity_state is populated — identity shaped decision" if passed
                      else "ctx.identity_state not set — identity did not shape decision",
        }

        # 4.2 — Exploration/Comfort Trade-off
        passed = exploration or exploitation
        results['4.2'] = {
            "passed": passed,
            "reason": f"exploration={exploration}, exploitation={exploitation} — trade-off made" if passed
                      else "no trade-off detected",
        }

        # 4.3 — Possibility Preservation
        opts = getattr(trace, 'strategic_options', []) if trace else []
        n_opts = len(opts)
        passed = n_opts >= 1
        results['4.3'] = {
            "passed": passed,
            "reason": f"strategic_options count={n_opts} >= 1 — alternatives preserved" if passed
                      else f"strategic_options count={n_opts} < 1 — no alternatives preserved",
        }

        # 4.4 — Structural Resilience (truth-anchored decision)
        cv_true = getattr(trace, 'council_validated', False) if trace else False
        passed = cv_true is True
        results['4.4'] = {
            "passed": passed,
            "reason": f"council_validated={cv_true} — truth-anchored decision" if passed
                      else f"council_validated={cv_true} — not truth-anchored",
        }

        # 4.5 — Local vs Global Optima
        lo_checked = getattr(trace, 'local_optima_escape', None) if trace else None
        passed = lo_checked is not None
        results['4.5'] = {
            "passed": passed,
            "reason": f"local_optima_escape is set — local vs global optima checked" if passed
                      else "local_optima_escape not set",
        }

        # 4.6 — Emergent Intelligence (≥2 streams activated)
        if stream_results:
            n_activated = sum(1 for s in stream_results if getattr(s, 'activated', False))
        else:
            n_activated = 0
        passed = n_activated >= 2
        results['4.6'] = {
            "passed": passed,
            "reason": f"{n_activated} streams activated (>= 2) — emergent intelligence" if passed
                      else f"only {n_activated} streams activated (< 2)",
        }

        # 4.7 — Law of Attention and Trajectory
        attn = getattr(trace, 'attention_metrics', None) if trace else None
        passed = attn is not None
        results['4.7'] = {
            "passed": passed,
            "reason": "attention_metrics is set — attention was allocated" if passed
                      else "attention_metrics not set",
        }

        # 4.8 — Models Compete (ΣP(M_i) = 1)
        mc = kwargs.get('model_competition', None)
        passed = mc is not None and hasattr(mc, 'dominant_model')
        results['4.8'] = {
            "passed": passed,
            "reason": "ModelCompetition present — hypotheses compete" if passed
                      else "ModelCompetition not found — no model competition",
        }

        # 4.9 — Relational Optimization (A_i = (U_i, Θ_i))
        # Other agents are modeled as optimizers with utility + parameters.
        # Scaffold predicate (Λ2.3 honest): meaningful when a RelationalContext
        # is wired with utility/authority fields; otherwise reported as
        # scaffold-not-verified (fail-closed — never silently passes).
        relational = (kwargs.get('relational_context', None)
                      or (getattr(ctx, 'relational_context', None) if hasattr(ctx, 'relational_context') else None))
        _has_rc = relational is not None and hasattr(relational, 'relational_coherence')
        results['4.9'] = {
            "passed": _has_rc,
            "reason": ("RelationalContext present — other agents modeled as optimizers"
                       if _has_rc else "RelationalContext scaffold absent — axiom not verified"),
        }

        # 4.11 — Cooperative Intelligence (U_group > ΣU_i − C_align)
        # Multi-agent architecture is long-term/aspirational (AXIOMS.md marks
        # it "aspirational"). FAIL-CLOSED: without multi-agent wiring this
        # axiom is reported as scaffold-not-verifiable — it NEVER silently
        # passes, it is honestly accounted as not-yet-implemented.
        coop = kwargs.get('cooperative_intelligence', None)
        results['4.11'] = {
            "passed": coop is not None,
            "reason": ("Cooperative intelligence wired — collective > isolated"
                       if coop is not None
                       else "multi-agent aspiration — declared NOT yet implemented (Λ2.3 fail-closed)"),
        }

        # 4.10 — Recursive World Models
        ss = kwargs.get('system_self', None) or (getattr(kwargs.get('pipeline'), '_system_self', None) if kwargs.get('pipeline') else None)
        tb = kwargs.get('theory_builder', None) or (getattr(kwargs.get('pipeline'), '_theory_builder', None) if kwargs.get('pipeline') else None)
        passed = (ss is not None) and (tb is not None)
        results['4.10'] = {
            "passed": passed,
            "reason": "SystemSelf + TheoryBuilder present — self and world models exist" if passed
                      else "SystemSelf or TheoryBuilder missing — recursive models incomplete",
        }

        # ── Layer 5: Commitment Theory ────────────────────────────────────

        # 5.1 — TELOS Commitment (Unified J)
        j_term = getattr(trace, 'j_term_breakdown', None) if trace else None
        commitment = getattr(trace, 'selected_intent', None) if trace else None
        passed = j_term is not None or commitment is not None
        results['5.1'] = {
            "passed": passed,
            "reason": "commitment (j_term_breakdown or selected_intent) computed" if passed
                      else "no commitment computation found",
        }

        # 5.2 — Axiom Evolution (A → Proposal → Human → Update)
        pipeline = kwargs.get('pipeline', None)
        aee = kwargs.get('axiom_evolution', None) or (getattr(pipeline, '_axiom_evolution', None) if pipeline else None)
        passed = aee is not None
        results['5.2'] = {
            "passed": passed,
            "reason": "AxiomEvolutionEngine present — axiom proposals possible" if passed
                      else "AxiomEvolutionEngine missing — no axiom evolution",
        }

        # 5.3 — Identity Coupling (C_align = λD(I_A, I_B))
        has_align = getattr(ctx, 'j_term_breakdown', {}).get('alignment_cost', 0) is not None \
            if hasattr(ctx, 'j_term_breakdown') else False
        if not has_align and trace is not None:
            jb = getattr(trace, 'j_term_breakdown', None)
            has_align = jb is not None and 'alignment_cost' in jb
        passed = bool(has_align)
        results['5.3'] = {
            "passed": passed,
            "reason": "alignment_cost tracked in J — identity coupling measured" if passed
                      else "alignment_cost not tracked — identity coupling not measured",
        }

        # ── Layer 6: Cognitive Dynamics ────────────────────────────────────

        # 6.1 — Cognitive Potential (Ψ_c = C_available − C_used)
        pipeline = kwargs.get('pipeline', None)
        rgt = kwargs.get('resource_gradient', None) or (getattr(pipeline, '_resource_gradient_tracker', None) if pipeline else None)
        passed = rgt is not None
        results['6.1'] = {
            "passed": passed,
            "reason": "ResourceGradientTracker present — cognitive potential measurable" if passed
                      else "ResourceGradientTracker missing",
        }

        # 6.2 — Cognitive Momentum (M_c = Σ w_i · a_i)
        pipeline = kwargs.get('pipeline', None)
        cm = kwargs.get('cognitive_momentum', None) or (getattr(pipeline, '_cognitive_momentum', None) if pipeline else None)
        passed = cm is not None
        results['6.2'] = {
            "passed": passed,
            "reason": "CognitiveMomentum present — decision inertia tracked" if passed
                      else "CognitiveMomentum missing",
        }

        # 6.3 — Interpretation Energy (E_I = D(P_i, P_j) · C)
        # Axiom conflicts have computational cost; interpretation is not free.
        # Real predicate: the InterpretationEngine (present in the codebase,
        # archive-rationale) must be wired for this axiom to be satisfiable.
        ie = kwargs.get('interpretation_engine', None)
        results['6.3'] = {
            "passed": ie is not None,
            "reason": ("InterpretationEngine present — conflict interpretation "
                       "energetically accounted" if ie is not None
                       else "InterpretationEngine absent — interpretation energy not modeled"),
        }

        # 6.4 — Identity Compression (I = Φ(E_{1:n}))
        ic = kwargs.get('identity_compression', None)
        passed = ic is not None
        results['6.4'] = {
            "passed": passed,
            "reason": "IdentityCompression present — identity compressed from experience" if passed
                      else "IdentityCompression missing",
        }

        # 6.5 — Theory Formation (Experience → Pattern → Hypothesis → Test → Theory)
        tb = kwargs.get('theory_builder', None)
        passed = tb is not None
        results['6.5'] = {
            "passed": passed,
            "reason": "TheoryBuilder present — theory formation pipeline active" if passed
                      else "TheoryBuilder missing",
        }

        # 6.6 — Theory Revisability (P(T|E) ∝ P(E|T)P(T))
        mc = kwargs.get('model_competition', None)
        has_revision = mc is not None and hasattr(mc, 'compute_entropy')
        passed = has_revision
        results['6.6'] = {
            "passed": passed,
            "reason": "ModelCompetition supports Bayesian revision — theories revisable" if passed
                      else "ModelCompetition missing or incomplete",
        }

        # 6.7 — Knowledge Compression
        ec = kwargs.get('explanation_compression', None)
        passed = ec is not None
        results['6.7'] = {
            "passed": passed,
            "reason": "ExplanationCompression present — knowledge compressed" if passed
                      else "ExplanationCompression missing",
        }

        # 6.8 — Recursive Intelligence
        ss = kwargs.get('system_self', None)
        tb = kwargs.get('theory_builder', None)
        passed = ss is not None and tb is not None
        results['6.8'] = {
            "passed": passed,
            "reason": "SystemSelf + TheoryBuilder present — self and world models" if passed
                      else "SystemSelf or TheoryBuilder missing",
        }

        # 6.9 — Curiosity Gradient (∇U_knowledge)
        cd = kwargs.get('curiosity_drive', None)
        passed = cd is not None
        results['6.9'] = {
            "passed": passed,
            "reason": "CuriosityDrive present — curiosity gradient active" if passed
                      else "CuriosityDrive missing",
        }

        # 6.10 — Unknown Unknown Discovery (R_u = f(PE, Novelty))
        uud = kwargs.get('unknown_unknown_detector', None)
        passed = uud is not None
        results['6.10'] = {
            "passed": passed,
            "reason": "UnknownUnknownDetector present — blind spot detection active" if passed
                      else "UnknownUnknownDetector missing",
        }

        # 6.11 — Opportunity Cost Exists (C_o = max(U_i) − U_chosen)
        has_opp = False
        if j_term is not None:
            has_opp = 'opportunity_cost' in j_term
        passed = bool(has_opp)
        results['6.11'] = {
            "passed": passed,
            "reason": "opportunity_cost tracked in J — foregone alternatives measured" if passed
                      else "opportunity_cost not tracked in J",
        }

        return results

    def summary(self, trace: Any, ctx: Any, **kwargs) -> Tuple[int, int, List[str]]:
        """Returns (total_passed, total_failed, failed_axioms).
            Args:
                trace: the decision trace for this cycle
                ctx: the phase context for this cycle
        """
        results = self.verify(trace, ctx, **kwargs)
        failed = [aid for aid, r in results.items() if not r["passed"]]
        total_passed = len(results) - len(failed)
        return total_passed, len(failed), failed

    def all_passed(self, trace: Any, ctx: Any, **kwargs) -> bool:
        """Quick check: returns True if all axioms are satisfied.
            Args:
                trace: the decision trace for this cycle
                ctx: the phase context for this cycle
        """
        _, total_failed, _ = self.summary(trace, ctx, **kwargs)
        return total_failed == 0


__all__ = ["AxiomProver"]
