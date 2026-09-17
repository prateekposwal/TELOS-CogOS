"""
Act Phase — Final action execution with governance checks and human-in-the-loop.

The Act Phase:
1. Syncs the Firewall DI threshold from MissionPolicy (Λ3.1 Recovery Mode)
2. Runs the Decision Firewall inspect
3. Checks if human review is needed (HumanGateway integration)
4. Converts the selected intent to an action via the domain adapter
5. Records semantic depths for the decision trace
"""

import logging
import numpy as np

from telos.core.phases.base import Phase, PhaseContext
from telos.core.governance.capability_authorization import (
    CapabilityAuthorization, CapabilityStatus,
)
from telos.core.governance.governor import (
    DecisionGovernor, GovernorInput, DecisionMode, GovernorDecision,
)
from telos.world.epistemic import derive_epistemic_state, EpistemicState
from telos.core.contracts.domain_model import WorldSpec

logger = logging.getLogger('telos_pipeline')


def _md_with_staleness(md_raw: float, prev: float, alpha: float,
                        catastrophe_ceiling: float, now_cycle: int,
                        last_validation_cycle) -> tuple:
    """Smooth mission-drift with stale-gap honesty (Λ6.5).

    The risk signal ``md_raw`` is the model's own per-step prediction error
    (recent_mean_gap). It is ONLY current when the model actually validated
    last cycle (an action flowed — the runtime records a prediction-vs-
    observation per acted cycle). During a governance-blocked streak NO
    records arrive, so recent_mean_gap FREEZES at its last acted value and a
    plain EWMA asymptotes to a permanent veto — frozen evidence presented as
    sustained divergence, the same misattribution that locked the 30K-cycle
    DI=0.3 plateau. Stale = no validation since before the previous cycle:
    decay the EWMA toward 0 (absence of validation is uncertainty, mirroring
    the act-then-learn doctrine) and suppress the frozen catastrophe read.

    Args:
        md_raw: raw recent-mean-gap this cycle.
        prev: previous filtered MD (EWMA carry).
        alpha: EWMA smoothing (0..1).
        catastrophe_ceiling: instantaneous veto threshold for md_raw.
        now_cycle: current pipeline cycle (0/None-safe).
        last_validation_cycle: cycle of the model's last REAL validation
            (None = never validated — fresh/untested).

    Returns:
        (md_filtered, catastrophe) — the EWMA value and the instantaneous
        catastrophe flag, staleness-adjusted.
    """
    filtered = alpha * md_raw + (1.0 - alpha) * prev
    catastrophe = md_raw > catastrophe_ceiling
    if last_validation_cycle is not None and now_cycle             and last_validation_cycle < (now_cycle - 1):
        # Frozen evidence is not current: decay, drop the frozen catastrophe.
        filtered = (1.0 - alpha) * prev
        catastrophe = False
    return filtered, catastrophe


# How many cycles without a REAL validation before the act gate treats the
# model as currently-unvalidated (act-then-learn). The per-step gap is only
# current for a few cycles in a world that shifts terrain every cycle — a
# 300-cycle truth window (council recency) would lock ACT out for ~300 cycles
# after ONE divergent step. The model's falsification record is untouched;
# this only stops a FROZEN gap from being presented as CURRENT truth.
ACT_FIDELITY_STALE_CYCLES = 5


class ActPhase(Phase):
    name = "act"

    def __init__(self, md_alpha: float = 0.3, md_catastrophe_ceiling: float = 2.0):
        # TELOS v6 over-conservatism fix (V1): EWMA smoothing state for mission
        # drift so a single noisy spike never instantaneously BLOCKs a healthy
        # cycle. `md_alpha` blends new readings; `md_catastrophe_ceiling` is the
        # absolute instantaneous MD above which we DO hard-veto regardless of
        # smoothing (true out-of-band spike).
        super().__init__()
        self._md_filtered: float = 0.0
        self._md_alpha: float = md_alpha
        self._md_catastrophe_ceiling: float = md_catastrophe_ceiling

    def _compute_governance(self, pipeline, ctx) -> tuple:
        """Compute CapabilityAuthorization + EpistemicState + GovernorDecision
        for this cycle.

        Uses only signals that are genuinely available; a missing signal is a
        permissive PASS so default behavior (all gates OK) is unchanged. Returns
        a tuple (capability, epistemic_state, governor_decision).

        Args:
            pipeline: the running pipeline (source of reality-gap tracker).
            ctx: the phase context for this cycle.
        """
        # Hoisted defaults (Λ2.3 latent-bug fix): `model_fidelity`, `tested`,
        # `spec`, `di`, `md` and `catastrophe` were only assigned inside the
        # no-override branch but referenced unconditionally by the shared
        # downstream computation (derive_epistemic_state, the WorldSpec block,
        # GovernorInput) — a pipeline with no tracker, or the documented
        # _governance_override test hook, crashed the whole governance
        # computation, silently swallowed by execute's except. One canonical
        # rule: a missing signal is a PERMISSIVE PASS (the module's own
        # contract); the hoisted permissive defaults honor that instead of
        # raising, and the else branch overwrites them with real signals.
        model_fidelity = None
        tested = False
        spec = None
        di = 1.0
        md = 0.0
        catastrophe = False

        # Optional injected authorization (tests / explicit override).
        override = getattr(ctx, '_governance_override', None)
        if override is not None and isinstance(override, CapabilityAuthorization):
            capability = override
        else:
            # ── Gather per-gate signals ──
            # model fidelity from the reality-gap tracker (Phase 4).
            model_id = "world"
            tracker = getattr(pipeline, '_reality_gap_tracker', None)
            if tracker is not None and not isinstance(tracker, type):
                try:
                    mf = tracker.model_fidelity(model_id, now_cycle=getattr(ctx, "cycle_count", None), stale_window=ACT_FIDELITY_STALE_CYCLES)
                    if isinstance(mf, (int, float)) and not isinstance(mf, bool):
                        model_fidelity = float(mf)
                        tested = True
                except Exception:
                    model_fidelity = None

            # Risk-coverage proxy = TRUE per-step prediction error (mean reality
            # gap), NOT the council's instantaneous MD (||horizon-end prediction -
            # current observation||), which is structurally large (~horizon
            # distance) in any moving world and would permanently veto ACT (the
            # no-action stagnation trap). The RealityGapTracker holds the
            # deferred one-cycle-ahead per-step error: a healthy model's gap -> 0;
            # a falsified model's gap stays high -> risk gate FAILs.
            # Untested model (no records yet) does NOT claim false failure: the
            # v6 act-then-learn permission lets a not-yet-falsified model act so
            # the first executed steps start feeding the real signal.
            md_raw = 0.0
            try:
                m = tracker.model("world")
                if m.tested and m.gap_history:
                    md_raw = float(m.recent_mean_gap)
            except Exception:
                md_raw = 0.0
            try:
                md_raw = float(md_raw)
            except (TypeError, ValueError):
                md_raw = 0.0
            # NOTE: no verdict-MD fallback. The risk signal is the model's OWN
            # per-step prediction error. An untested model claims NO failure
            # (act-then-learn, matching the model_fidelity gate's treatment of
            # unvalidated models in high-observability worlds); a tested model
            # vetoes only on genuine, sustained prediction error.

            # TELOS v6 (over-conservatism fix V1): smooth mission drift so a
            # single noisy spike does NOT instantaneously BLOCK a healthy cycle.
            # Sentence of the fix: "transient jitter -> continue/explore (log);
            # sustained divergence -> refuse." We keep an EWMA of MD and gate the
            # 0.75 risk threshold and the governor's MD on the SMOOTHED value,
            # while reserving an INSTANTANEOUS hard veto for a catastrophe ceiling
            # (true out-of-band spike). This does NOT weaken genuine FAIL gates.
            alpha = getattr(self, '_md_alpha', 0.3)
            prev = getattr(self, '_md_filtered', 0.0)
            try:
                prev = float(prev)
            except (TypeError, ValueError):
                prev = 0.0
            try:
                _m = tracker.model("world")
                _last_v = _m.last_validation_cycle
            except Exception:
                _last_v = None
            md, catastrophe = _md_with_staleness(
                md_raw=md_raw,
                prev=prev,
                alpha=alpha,
                catastrophe_ceiling=float(getattr(self, '_md_catastrophe_ceiling', 2.0)),
                now_cycle=int(getattr(ctx, 'cycle_count', 0) or 0),
                last_validation_cycle=_last_v,
            )
            self._md_filtered = md
            raw_verdict_md = 0.0
            verdict = getattr(ctx, 'verdict', None)
            if verdict is not None:
                try:
                    raw_verdict_md = float(getattr(verdict, 'mission_drift', 0.0) or 0.0)
                except (TypeError, ValueError):
                    raw_verdict_md = 0.0
            # World-horizon-scaled catastrophe veto (Item 1). The verdict's
            # mission_drift compares the HORIZON-end simulation landing against
            # the current observation — a horizon-length displacement whose
            # legitimate maximum is the WORLD's own state-space diameter
            # (corner-to-corner ≈ 5.66 on the 5×5 GridWorld), ABOVE both the
            # old fixed 4.0 bar and the council's own 5.0 drift tolerance. A
            # fixed ceiling below the world's diameter vetoed ~24% of healthy
            # cycles as `risk_coverage` catastrophes (the [4,2] governor
            # risk_coverage limit cycle). Scale the ceiling from the
            # simulator's declared world extent when the domain exposes one;
            # unknown geometry keeps the legacy absolute bar so the safety
            # floor is unchanged — an MD beyond the world's physical maximum
            # still vetoes (only an impossible prediction can exceed it).
            catastrophe_ceiling = 4.0  # legacy absolute bar (unknown geometry)
            try:
                sim_ = getattr(getattr(pipeline, 'config', None), 'simulator', None)
                if sim_ is not None and not isinstance(sim_, type) \
                        and callable(getattr(sim_, 'world_spec', None)):
                    extent = getattr(sim_, 'world_extent', None)
                    if isinstance(extent, (int, float)) and not isinstance(extent, bool) \
                            and extent > 1.0:
                        n_dims = max(int(np.asarray(ctx.state).shape[0])
                                     if ctx.state is not None else 2, 1)
                        catastrophe_ceiling = float(extent - 1.0) * float(np.sqrt(n_dims))
            except Exception:
                catastrophe_ceiling = 4.0
            if raw_verdict_md > catastrophe_ceiling:
                catastrophe = True

            # DI / council signals for causal-confidence + recovery.
            di = 1.0
            if verdict is not None:
                di = getattr(verdict, 'decision_integrity', 1.0) or 1.0
            try:
                di = float(di)
            except (TypeError, ValueError):
                di = 1.0
            # Unfloored evidence-integrity: reflect evidence-weighted dissent, NOT
            # the DissentFloor cap. Prevents a single dissenting validator from
            # spuriously failing the causal/recovery capability gates (V2).
            di_evidence = di
            if verdict is not None:
                ev = getattr(verdict, 'evidence_integrity', None)
                if ev is None:
                    ev = getattr(verdict, 'decision_integrity', di)
                try:
                    di_evidence = float(ev)
                except (TypeError, ValueError):
                    di_evidence = di

            # observability from the world spec if available.
            observability_status = CapabilityStatus.PASS
            spec = None
            adapter = getattr(pipeline, 'config', None)
            adapter = getattr(adapter, 'adapter', None) if adapter is not None else None
            if adapter is not None and not isinstance(adapter, type) \
                    and callable(getattr(adapter, 'world_spec', None)):
                try:
                    spec = adapter.world_spec()
                    # Only a genuine WorldSpec counts. A MagicMock (unit-test
                    # pipeline) or arbitrary object must NOT leak garbage into
                    # the gates — treat it as no constraint (permissive PASS).
                    if spec is not None and not isinstance(spec, WorldSpec):
                        spec = None
                    elif spec is not None and hasattr(spec, 'observability')\
                            and getattr(spec, 'observability', 'high') in ("low", "partial"):
                        observability_status = CapabilityStatus.LIMITED
                except Exception:
                    spec = None

            # model_fidelity gate: a validated model below 0.5 fidelity is FAIL.
            model_fidelity_status = CapabilityStatus.PASS
            if tested and model_fidelity is not None and model_fidelity < 0.5:
                model_fidelity_status = CapabilityStatus.FAIL
            # Evidence-bounded calibration (benchmark Task C finding): an UNTESTED
            # model in a LOW/PARTIAL-observability world is genuinely insufficient
            # to justify ACT — we cannot see the world well AND we have not
            # validated the model. High-observability untested worlds may still
            # act-then-learn (returns PASS there). This TIGHTENS a justified gate;
            # it does NOT relax any conjunctive veto.
            elif (not tested) and observability_status == CapabilityStatus.LIMITED:
                model_fidelity_status = CapabilityStatus.FAIL

            # risk_coverage gate: high mission drift => unacceptable risk => FAIL.
            # Uses SMOOTHED md (sustained divergence) OR an instantaneous
            # catastrophe spike (true out-of-band). Transient jitter alone,
            # below the ceiling, does NOT fail the gate (over-conservatism fix).
            risk_coverage_status = CapabilityStatus.PASS
            if md > 0.75 or catastrophe:
                risk_coverage_status = CapabilityStatus.FAIL

            # causal_confidence / recovery from DI.
            causal_status = CapabilityStatus.PASS
            if di_evidence < 0.3:
                causal_status = CapabilityStatus.FAIL
            recovery_status = CapabilityStatus.PASS
            if di_evidence < 0.4:
                recovery_status = CapabilityStatus.FAIL

            # authority from world spec authorized_modes.
            authority_status = CapabilityStatus.PASS
            authorized_modes = None
            if spec is not None and hasattr(spec, 'authorized_modes'):
                authorized_modes = set(spec.authorized_modes)
                if DecisionMode.ACT.value not in (authorized_modes or set()):
                    authority_status = CapabilityStatus.FAIL

            capability = CapabilityAuthorization(
                observability=observability_status,
                model_fidelity=model_fidelity_status,
                action_validity=CapabilityStatus.PASS,
                risk_coverage=risk_coverage_status,
                causal_confidence=causal_status,
                recovery=recovery_status,
                authority=authority_status,
            )

        # ── Epistemic state (Phase 5) ──
        tripartite = getattr(pipeline, '_tripartite_u', None)
        composite_u = 0.0
        if tripartite is not None:
            composite_u = getattr(tripartite, 'composite', 0.0) or 0.0
        try:
            composite_u = float(composite_u)
        except (TypeError, ValueError):
            composite_u = 0.0
        epistemic_state = derive_epistemic_state(
            model_fidelity=model_fidelity,
            tested=tested,
            composite_uncertainty=composite_u,
            has_model=True,
        )

        # ── World authorized modes + escalation policy (Phase 6 / v6 policy) ──
        # `spec` is the guarded WorldSpec (or None) computed above in the
        # observability block — recycle it rather than re-deriving unguarded.
        authorized_modes = None
        escalation_policy = "advisory"
        if spec is not None:
            authorized_modes = set(spec.authorized_modes)
            escalation_policy = getattr(spec, "escalation_policy", "advisory") or "advisory"

        # ── Governor ──
        verdict = getattr(ctx, 'verdict', None)
        escalation = bool(getattr(verdict, 'escalation_requested', False)) if verdict else False
        human_authorized = bool(getattr(ctx, 'human_authorized', False))
        governor = getattr(pipeline, '_decision_governor', None)
        if governor is None or not callable(getattr(governor, 'evaluate', None)):
            governor = DecisionGovernor()

        decision = governor.evaluate(GovernorInput(
            capability=capability,
            epistemic_state=epistemic_state,
            authorized_modes=authorized_modes,
            DI=di,
            MD=md,
            escalation_requested=escalation,
            escalation_policy=escalation_policy,
            human_authorized=human_authorized,
            hard_constraint_violation=catastrophe,
        ))
        # A governance decision that is not a real GovernorDecision (e.g. a
        # MagicMock leaking from a unit-test mock pipeline) is invalid — fall
        # back to a fresh DecisionGovernor so a bogus "decision" can never
        # authorize ACT.
        if not isinstance(decision, GovernorDecision):
            logger.warning("DecisionGovernor returned a non-GovernorDecision — "
                           "recomputing with a fresh governor")
            decision = DecisionGovernor().evaluate(GovernorInput(
                capability=capability,
                epistemic_state=epistemic_state,
                authorized_modes=authorized_modes,
                DI=di,
                MD=md,
                escalation_requested=escalation,
                escalation_policy=escalation_policy,
                human_authorized=human_authorized,
                hard_constraint_violation=catastrophe,
            ))
        return capability, epistemic_state, decision

    def execute(self, pipeline, ctx: PhaseContext) -> None:
        # P1.3: Sync Firewall DI threshold from MissionPolicy before inspect
        try:
            infra = getattr(pipeline, '_infra_manager', None)
            if infra and hasattr(infra, 'policy') and infra.policy is not None:
                threshold = infra.policy.firewall_di_threshold
                old_threshold = pipeline._firewall.config.min_decision_integrity
                pipeline._firewall.set_di_threshold(threshold)
                logger.debug(f"Firewall: DI threshold synced to {threshold:.3f} (was {old_threshold:.3f})")
            else:
                logger.warning("Firewall: DI threshold sync skipped — no infra_manager")
        except Exception as e:
            logger.warning(f"Firewall: DI threshold sync failed — {e}")

        ctx.firewall_verdict = pipeline._firewall.inspect(
            ctx.world, ctx.selected_intent,
            council_validated=ctx.verdict.validated if ctx.verdict else True,
            decision_integrity=ctx.verdict.decision_integrity if ctx.verdict else 1.0,
            mission_violation=False,
        )

        ctx.council_blocked = not (ctx.verdict.validated if ctx.verdict else True)
        ctx.firewall_blocked = not ctx.firewall_verdict.passed
        ctx.governance_blocked = ctx.firewall_blocked or (ctx.council_blocked and pipeline._firewall.config.block_on_council_rejection)

        # HumanGateway override: if firewall blocked AND escalation requested, ask human
        if ctx.firewall_blocked and ctx.verdict and ctx.verdict.escalation_requested:
            human_gateway = getattr(pipeline, 'human_gateway', None)
            if human_gateway is not None:
                try:
                    verdict = human_gateway.review(
                        intent=ctx.selected_intent,
                        council_signals=[
                            {"validator": s.validator_name, "passed": s.passed,
                             "confidence": s.confidence, "reason": s.reason}
                            for s in (ctx.verdict.signals if ctx.verdict else [])
                        ],
                        decision_integrity=ctx.verdict.decision_integrity if ctx.verdict else 1.0,
                        mission_drift=ctx.verdict.mission_drift if ctx.verdict else 0.0,
                        blocking_validator=ctx.firewall_verdict.blocked_by,
                        context={"cycle": ctx.cycle_count,
                                  "reason": ctx.firewall_verdict.reason},
                    )
                    if verdict.approved:
                        ctx.governance_blocked = False
                        ctx.firewall_blocked = False
                        ctx.blocking_reason = ""
                        logger.info(
                            f"Cycle {ctx.cycle_count}: HumanGateway overrode firewall block — "
                            f"{verdict.override_reason}"
                        )
                    else:
                        logger.warning(
                            f"Cycle {ctx.cycle_count}: HumanGateway upheld firewall block — "
                            f"{verdict.override_reason}"
                        )
                except Exception as e:
                    logger.warning(f"HumanGateway firewall review failed: {e}")

        # Handle escalation: check if human review is needed
        ctx.escalation_pending = False
        if ctx.verdict and ctx.verdict.escalation_requested and not ctx.governance_blocked:
            ctx.escalation_pending = True

            # P1.6: Check HumanGateway for escalation review
            human_gateway = getattr(pipeline, 'human_gateway', None)
            if human_gateway is not None:
                try:
                    should_review = human_gateway.should_review(
                        council_validated=ctx.verdict.validated,
                        decision_integrity=ctx.verdict.decision_integrity,
                    )
                    if should_review:
                        escalation_data = {
                            "intent": ctx.selected_intent,
                            "council_signals": [
                                {
                                    "validator": s.validator_name,
                                    "passed": s.passed,
                                    "confidence": s.confidence,
                                    "reason": s.reason,
                                    "verdict": s.verdict,
                                }
                                for s in (ctx.verdict.signals if ctx.verdict else [])
                            ],
                            "decision_integrity": ctx.verdict.decision_integrity if ctx.verdict else 1.0,
                            "mission_drift": ctx.verdict.mission_drift if ctx.verdict else 0.0,
                            "blocking_validator": ctx.verdict.blocking_validator if ctx.verdict else None,
                            "context": {
                                "cycle": ctx.cycle_count,
                                "escalation_reason": ctx.verdict.escalation_reason if ctx.verdict else None,
                            },
                        }
                        verdict = human_gateway.review(
                            intent=ctx.selected_intent,
                            council_signals=escalation_data["council_signals"],
                            decision_integrity=escalation_data["decision_integrity"],
                            mission_drift=escalation_data["mission_drift"],
                            blocking_validator=escalation_data["blocking_validator"],
                            context=escalation_data["context"],
                        )
                        if not verdict.approved:
                            ctx.governance_blocked = True
                            ctx.blocking_reason = "human_review_blocked"
                            logger.warning(
                                f"Cycle {ctx.cycle_count}: HumanGateway BLOCKED action — "
                                f"{verdict.override_reason}"
                            )
                        else:
                            logger.info(
                                f"Cycle {ctx.cycle_count}: HumanGateway approved action — "
                                f"{verdict.override_reason}"
                            )
                except Exception as e:
                    logger.warning(f"HumanGateway review failed: {e}")

            if not ctx.governance_blocked:
                logger.warning(
                    f"Council escalation: {ctx.verdict.escalation_reason}. "
                    "Proceeding with action but escalation logged."
                )

        firewall_passed = ctx.firewall_verdict.passed
        council_ok = (ctx.verdict.validated if ctx.verdict else True) or (ctx.verdict and ctx.verdict.escalation_requested)

        # ── TELOS v6 governance (Phases 6/7/8): capability authorization +
        #    DecisionGovernor. This is STRUCTURAL — before any action vector is
        #    constructed, the governor must authorize ACT. If not authorized,
        #    we skip the inten_to_action call entirely (no action emitted). ──
        governor_allows_act = True
        try:
            capability, epistemic_state, governor_decision = self._compute_governance(pipeline, ctx)
            ctx.capability_authorization = capability
            ctx.epistemic_state = epistemic_state
            ctx.governor_decision = governor_decision
            ctx.decision_mode = governor_decision.mode
            # Audit Item 1 (decision-mode telemetry): record WHY the cycle
            # did not act — the failed capability gate(s) (e.g. model_fidelity,
            # risk_coverage, causal_confidence, recovery, authority) — on the
            # context on EVERY cycle, INCLUDING DEFER/BLOCK (Lambda 2.3: the
            # reason is never silently dropped). The governor's metadata
            # carries the gates that failed when it deferred/blocked on
            # capability; the capability fallback covers the other hard-stop
            # paths (ABSTAIN on low DI -> causal_confidence/recovery FAIL,
            # BLOCK on high MD -> risk_coverage FAIL). Readable after
            # execute() so the trace and decision log can show "DEFER —
            # model_fidelity" instead of a silent no-op. try/except:
            # telemetry must never break the act gate.
            try:
                _failed = list(governor_decision.metadata.get("failed_gates") or [])
                if not _failed and capability is not None:
                    _failed = [g for g in capability.failed_gates() if isinstance(g, str)]
                ctx.blocked_by_gate = ",".join(sorted(_failed)) if _failed else None
            except Exception:
                ctx.blocked_by_gate = None
            # ESCALATE is a deliberate per-world policy (see GovernorDecision.hard_stop):
            #   advisory  -> proceed + log (existing behavior preserved)
            #   required  -> HARD STOP until distinct human authorization (safety-critical)
            # DEFER/ABSTAIN/BLOCK always structurally suppress action emission.
            ctx.no_action = governor_decision.hard_stop
            if governor_decision.hard_stop:
                governor_allows_act = False
                ctx.blocking_reason = governor_decision.reason
                if governor_decision.mode == DecisionMode.BLOCK:
                    # A governor BLOCK is a genuine block — preserve the
                    # governance_blocked semantics that BenchmarkMetrics counts.
                    ctx.governance_blocked = True
                logger.warning(
                    f"Cycle {ctx.cycle_count}: DecisionGovernor → {governor_decision.mode.value} — "
                    f"{governor_decision.reason}"
                )
            else:
                ctx.escalation_pending = ctx.escalation_pending or governor_decision.mode == DecisionMode.ESCALATE
        except Exception as e:
            logger.warning(f"Cycle {ctx.cycle_count}: governance computation failed — {e}")

        if firewall_passed and council_ok and not ctx.governance_blocked and governor_allows_act:
            if pipeline.config.adapter and ctx.selected_intent:
                # P1: validate state dimensionality against the adapter's declared
                # dimension (acceptance: dimensions validated, no accidental
                # shape-inference-only). If the adapter declares one, it must match
                # the actual state vector — a mismatch is a loud error, not a NaN.
                declared = pipeline.config.adapter.declared_state_dim()
                # Only enforce when the adapter genuinely declares an integer
                # dimension. Non-integer/missing (None or, e.g., a MagicMock in
                # unit tests) means "no declared dimension" → skip validation.
                if isinstance(declared, int) and not isinstance(declared, bool) \
                        and ctx.state is not None and declared != ctx.state.shape[0]:
                    raise ValueError(
                        f"State dimension mismatch: adapter '{pipeline.config.adapter.name}' "
                        f"declares state_dim={declared} but actual state has shape "
                        f"{ctx.state.shape}. Refusing to act (no silent dimension inference)."
                    )
                state_dim = ctx.state.shape[0]
                mission_dir = np.zeros(state_dim)

                ctx.selected_action = pipeline.config.adapter.intent_to_action(
                    ctx.selected_intent, ctx.state, mission_dir
                )
                # Honest one-step prediction: the model's own landing prediction
                # for the action that will ACTUALLY execute, computed through the
                # real transition. The council/runtime MD and the reality gap then
                # compare one-step-ahead predictions against the next observation -
                # a true per-step prediction error (not a horizon-distance artifact
                # that would permanently veto ACT in any moving world).
                try:
                    sim_ = getattr(pipeline.config, 'simulator', None)
                    if sim_ is not None and ctx.selected_action is not None                             and not isinstance(sim_, type):
                        # MagicMock leak guard: a mock simulator returns a
                        # shape-(0,) array that would poison the causal
                        # annotation broadcast below — only real transitions
                        # with the correct state shape may set the prediction.
                        landing = sim_.transition(
                            ctx.state.copy(), np.asarray(ctx.selected_action, dtype=float))
                        if landing is not None and not isinstance(landing, type):
                            larr = np.asarray(landing, dtype=float)
                            if larr.shape == ctx.state.shape:
                                ctx.predicted_state = larr
                except Exception as e:
                    logger.warning(f"act: predicted_state computation failed: {e}")
                # P1 D1: Causal annotations for the selected action
                predicted = getattr(ctx, 'predicted_state', None)
                ctx.causal_annotations = {
                    "intended_effect": {
                        "action_type": ctx.selected_intent.intent_type if ctx.selected_intent else "unknown",
                        "target_position": ctx.selected_action.tolist() if ctx.selected_action is not None else None,
                        "expected_outcome": "reduce_distance_to_goal",
                    },
                    "unintended_consequences": {
                        "action_vector_magnitude": float(np.linalg.norm(ctx.selected_action)) if ctx.selected_action is not None else 0.0,
                        "governance_blocked": ctx.governance_blocked,
                        "council_signals": [
                            s.validator_name for s in (ctx.verdict.signals if ctx.verdict else [])
                            if not s.passed
                        ],
                    },
                    "downstream_shift": {
                        "predicted_state_diff": (
                            (predicted - ctx.state).tolist()
                            if predicted is not None and ctx.state is not None
                            else None
                        ),
                        "world_model_updated": True,
                    },
                }
                if ctx.escalation_pending:
                    logger.info(
                        f"Action taken despite escalation: {ctx.selected_intent.intent_type} "
                        f"(DI={ctx.verdict.decision_integrity:.3f})"
                    )
        else:
            ctx.blocking_reason = ctx.firewall_verdict.blocked_by or (ctx.verdict.blocking_validator if ctx.verdict else None) or "governance"
            if ctx.verdict and ctx.verdict.escalation_requested:
                ctx.blocking_reason += f" [ESCALATED: {ctx.verdict.escalation_reason}]"
            logger.warning(
                f"Governance BLOCKED action. Check: {ctx.blocking_reason}. "
                f"DI={ctx.verdict.decision_integrity:.3f}"
            )

        # ── Real tool-use channel (audited ActionExecutor) ──────────────────
        # Runs AFTER the cycle's governance outcome is final. The authoritative
        # gate lives in _maybe_execute_tool's in-method guard: a council block,
        # firewall block, or governor hard-stop records a governance_blocked_cycle
        # audit and NO command runs; only a fully-cleared cycle reaches the
        # executor, which re-audits through the firewall + hard allowlist. Every
        # outcome — executed or blocked — lands in the DecisionTrace as
        # tool_audit and in the firewall's governance signals (audit-first:
        # blocked attempts are visible, never silent).
        try:
            self._maybe_execute_tool(pipeline, ctx)
        except Exception as e:
            logger.warning(f"Cycle {ctx.cycle_count}: act tool execution failed: {e}")

        # Emit readiness signal based on action outcome
        if ctx.governance_blocked:
            pipeline.readiness_engine.emit_signal("action_blocked", strength=0.5)
        else:
            pipeline.readiness_engine.emit_signal("action_completed", strength=1.0)

        if ctx.world:
            depths = ctx.world.metadata.get("semantic_depths", [])
            for d in depths:
                ctx.semantic_depths.append({
                    "entity_id": d.entity_id,
                    "observable_state": d.observable_state,
                    "historical_context": d.historical_context,
                    "mission_context": d.mission_context,
                    "semantic_identity": d.semantic_identity,
                })


    def _maybe_execute_tool(self, pipeline, ctx) -> None:
        """Invoke the audited ActionExecutor when a tool intent was selected.

        Gates (ALL must hold, else nothing runs and a block record is made):
          1. pipeline.config.action_executor is configured (operator opted in);
          2. the selected intent is a tool intent (execute_tool) whose params
             carry a tool_permission spec the council has seen;
          3. per-cycle operator permission exists (config operator_tool_permission
             or a genuine HumanGateway approval this cycle).
        The executor itself re-audits through DecisionFirewall.inspect and
        validates the request against its hard allowlist before any subprocess
        runs. The full audit record is written to ctx.tool_audit and appended
        to the firewall's governance signals.

        Args:
            pipeline: the running pipeline (config.action_executor, firewall).
            ctx: the phase context for this cycle.
        """
        executor = getattr(getattr(pipeline, 'config', None), 'action_executor', None)
        if executor is None or not callable(getattr(executor, 'execute', None)):
            return
        intent = ctx.selected_intent
        if intent is None or intent.intent_type != "execute_tool":
            return
        # Defense in depth: NEVER run a real command on a cycle the council,
        # firewall, or governor blocked (belt-and-braces beyond the gate the
        # act phase already enforces at the call site).
        if getattr(ctx, 'governance_blocked', False) \
                or getattr(ctx, 'council_blocked', False) \
                or getattr(ctx, 'firewall_blocked', False):
            from telos.core.actions.executor import ActionExecution
            block = ActionExecution(
                tool_name=intent.params.get("tool_name") or "unknown",
                command="", allowed=False,
                blocked_reason="governance_blocked_cycle",
                permitted_by="",
            )
            ctx.tool_audit = block.to_dict()
            logger.warning(
                f"Cycle {ctx.cycle_count}: tool intent {block.tool_name} BLOCKED — "
                "cycle is governance-blocked (council/firewall/governor)"
            )
            return
        operator_grant = bool(getattr(
            getattr(pipeline, 'config', None), 'operator_tool_permission', False))
        operator_grant = operator_grant or bool(getattr(ctx, 'human_authorized', False))
        if not operator_grant:
            from telos.core.actions.executor import ToolPermission, ActionExecution
            block = ActionExecution(
                tool_name=intent.params.get("tool_name") or "unknown",
                command="", allowed=False,
                blocked_reason="no_operator_permission",
                permitted_by="",
            )
            ctx.tool_audit = block.to_dict()
            if ctx.firewall_verdict is not None:
                ctx.firewall_verdict.governance_signals.append({
                    "check": "tool_audit",
                    "passed": False,
                    "blocked_reason": "no_operator_permission",
                })
            logger.warning(
                f"Cycle {ctx.cycle_count}: tool intent {block.tool_name} BLOCKED — "
                "no operator permission this cycle (HumanGateway discipline)"
            )
            return

        from telos.core.actions.executor import ToolPermission
        spec = intent.params.get("tool_permission")
        if not isinstance(spec, dict) or not spec.get("tool_name"):
            from telos.core.actions.executor import ActionExecution
            block = ActionExecution(
                tool_name=intent.params.get("tool_name") or "unknown",
                command="", allowed=False,
                blocked_reason="missing_tool_permission_spec",
                permitted_by="",
            )
            ctx.tool_audit = block.to_dict()
            logger.warning(
                f"Cycle {ctx.cycle_count}: tool intent BLOCKED — no tool_permission spec"
            )
            return

        permission = ToolPermission(
            tool_name=spec["tool_name"],
            args=list(spec.get("args", []) or []),
            cwd=spec.get("cwd") or getattr(executor, 'workspace_root', None),
            permitted_by="human_gateway" if getattr(ctx, 'human_authorized', False) else "operator",
            approved_message=spec.get("approved_message"),
            permission_id=spec.get("permission_id") or f"cycle_{ctx.cycle_count}",
        )
        execution = executor.execute(
            permission,
            firewall=pipeline._firewall,
        )
        ctx.tool_audit = execution.to_dict()
        if ctx.firewall_verdict is not None:
            ctx.firewall_verdict.governance_signals.append(
                executor.audit_entry(execution)
            )
        status = "EXECUTED" if execution.allowed else f"BLOCKED ({execution.blocked_reason})"
        logger.info(
            f"Cycle {ctx.cycle_count}: tool audit — {execution.tool_name} {status} "
            f"({execution.command[-80:]})"
        )
