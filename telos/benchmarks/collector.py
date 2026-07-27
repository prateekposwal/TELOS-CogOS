"""BenchmarkCollector — collects comprehensive cognition metrics."""
from telos.benchmarks.metrics import *
from telos.benchmarks.metrics.report import EpochSummary, BaselineComparison, BenchmarkReport
from telos.benchmarks.metrics.io import save_baseline, load_baseline

class BenchmarkCollector:
    """Collects, stores, and reports benchmark metrics every cycle.

    Each call to collect() takes a projection of the hidden cognitive
    state X(t) and records it as a BenchmarkSnapshot. The snapshot is
    organized along 7 conserved cognitive process axes, then aggregated
    through a 4-level hierarchy: Metrics → Subsystem → System → Mission.

    Usage:
        collector = BenchmarkCollector()

        # In pipeline_finalize.py, after axiom verification:
        collector.collect(pipeline, trace, ctx)

        # On demand:
        report = collector.get_report()
        print(report.to_markdown())

        # Save baseline:
        collector.save_baseline("/tmp/telos_baseline.json")
    """

    def __init__(self, output_dir: str = "telos/benchmarks/data",
                 max_snapshots: int = 5000):
        self.output_dir = output_dir
        self._snapshots: List[BenchmarkSnapshot] = []
        self._max_snapshots = max_snapshots
        self._session_start = time.time()
        self._session_id = datetime.now().strftime("session_%Y%m%d_%H%M%S")
        self._baseline_path: Optional[str] = None
        os.makedirs(output_dir, exist_ok=True)

    # ── Collection ──────────────────────────────────────────────

    def collect(self, pipeline: Any, trace: Any, ctx: Any) -> BenchmarkSnapshot:
        """Collect a full benchmark snapshot from the pipeline state.

        Called from pipeline_finalize.py once per cycle.
        `pipeline` is the TelosV14Pipeline instance.
        `trace` is the DecisionTrace for this cycle.
        `ctx` is the PipelineContext.
        """
        snapshot = self._build_snapshot(pipeline, trace, ctx)
        self._snapshots.append(snapshot)
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots = self._snapshots[-self._max_snapshots:]
        self._auto_persist()
        return snapshot

    def _build_snapshot(self, pipeline: Any, trace: Any, ctx: Any) -> BenchmarkSnapshot:
        """Extract all metrics from pipeline subsystems — projections of X(t)."""
        cycle = getattr(ctx, 'cycle_count', 0)

        # ═══════════════════════════════════════════════════════════
        # 1. Perception — prediction health, uncertainty, surprise
        # ═══════════════════════════════════════════════════════════

        # Prediction/estimation error from trace
        state_estimation_error = getattr(trace, 'prediction_error', 0.0) or 0.0
        # Try curiosity drive for prediction error as well
        cd = getattr(pipeline, '_curiosity_drive', None)
        if cd is not None:
            cd_report = cd.get_report() if hasattr(cd, 'get_report') else {}
            cd_pred_error = cd_report.get('prediction_error', None)
            if cd_pred_error is not None:
                state_estimation_error = cd_pred_error

        # Surprise rate from unknown unknown detector
        uud = getattr(pipeline, '_unknown_unknown_detector', None)
        if uud is not None and hasattr(uud, 'surprise_rate'):
            surprise_rate = uud.surprise_rate
        else:
            surprise_rate = 0.0

        uu_discovery = 0.0
        if uud is not None:
            if hasattr(uud, 'discovery_rate'):
                uu_discovery = uud.discovery_rate
            elif hasattr(uud, 'n_unknown_unknowns'):
                uu_discovery = min(uud.n_unknown_unknowns / max(cycle, 1), 1.0)

        # Forecast accuracy from model competition
        mc = getattr(pipeline, '_model_competition', None)
        if mc is not None and hasattr(mc, 'dominant_model'):
            dm = getattr(mc, 'dominant_model', None)
            if dm is not None and hasattr(dm, 'accuracy'):
                forecast_accuracy = dm.accuracy
            else:
                forecast_accuracy = getattr(mc, 'ensemble_accuracy', 0.5)
        else:
            forecast_accuracy = 0.5

        # Counterfactual accuracy from simulation engine
        sim = getattr(pipeline, '_simulator', None)
        if sim is not None and hasattr(sim, 'counterfactual_accuracy'):
            counterfactual_accuracy = sim.counterfactual_accuracy
        else:
            counterfactual_accuracy = 0.5

        # ═══════════════════════════════════════════════════════════
        # 2. Learning — curiosity, compression, knowledge yield
        # ═══════════════════════════════════════════════════════════

        curiosity_report = getattr(trace, 'curiosity_state', None) or {}
        if not curiosity_report and cd is not None:
            curiosity_report = cd.get_report() if hasattr(cd, 'get_report') else {}
        curiosity_level = curiosity_report.get('curiosity_level', 0.5)
        learning_rate = curiosity_report.get('learning_rate', 0.0)
        boredom_count = curiosity_report.get('boredom_count', 0)

        ic = getattr(pipeline, '_identity_compression', None)
        compression_rate = ic.overall_compression_rate if ic and hasattr(ic, 'overall_compression_rate') else 0.5

        exploration_cycles = curiosity_report.get('exploration_cycles', 0)
        exploitation_cycles = curiosity_report.get('exploitation_cycles', 0)
        total_ce = exploration_cycles + exploitation_cycles
        exploration_ratio = exploration_cycles / max(total_ce, 1)

        # Knowledge Yield Pipeline
        tb = getattr(pipeline, '_theory_builder', None)
        if tb is not None:
            ky_observations = getattr(tb, 'total_experiences', 0)
            ky_theories = len(getattr(tb, '_theories', {}))
            ky_predictions = getattr(tb, 'total_predictions', 0)
            ky_validated = getattr(tb, 'validated_predictions', 0)
            ky_principles = getattr(tb, 'general_principles', 0)
        else:
            ky_observations = ky_theories = ky_predictions = ky_validated = ky_principles = 0

        # ═══════════════════════════════════════════════════════════
        # 3. Identity — coherence, continuity, propagation
        # ═══════════════════════════════════════════════════════════

        ie = getattr(pipeline, '_identity_entropy', None)
        identity_entropy = 0.0
        if ie is not None:
            if hasattr(ie, 'current_entropy'):
                identity_entropy = ie.current_entropy
            elif hasattr(ie, 'entropy'):
                identity_entropy = ie.entropy

        identity_state = getattr(trace, 'identity_state', None) or {}
        identity_continuity = identity_state.get('continuity', 0.5) if isinstance(identity_state, dict) else 0.5
        relational_coherence = getattr(trace, 'relational_coherence', 1.0) or 1.0

        # Identity Propagation
        mission_alignment = getattr(trace, 'mission_alignment', 0.5) or 0.5
        project_alignment = getattr(trace, 'project_alignment', 0.5) or 0.5
        decision_alignment = getattr(trace, 'decision_alignment', 0.5) or 0.5

        # ═══════════════════════════════════════════════════════════
        # 4. Knowledge — representation ecology, epistemic capital
        # ═══════════════════════════════════════════════════════════

        eco = getattr(pipeline, '_ecosystem', None)
        if eco is not None:
            eco_dict = eco.to_dict() if hasattr(eco, 'to_dict') else {}
            rep_age = eco_dict.get('mean_representation_age', 0.0)
            rep_diversity = eco_dict.get('representation_diversity', 0.0)
            retirement_rate = eco_dict.get('retirement_rate', 0.0)
            bridge_density = eco_dict.get('bridge_density', 0.0)
            reuse_rate = eco_dict.get('reuse_rate', 0.0)
            compression_achieved = eco_dict.get('compression_achieved', compression_rate)
            bridge_potential = eco_dict.get('bridge_potential_avg', 0.0)
        else:
            rep_age = rep_diversity = retirement_rate = 0.0
            bridge_density = reuse_rate = 0.0
            compression_achieved = compression_rate
            bridge_potential = 0.0

        # Epistemic Capital (renamed from Belief Capital)
        bcm = getattr(pipeline, '_belief_capital', None)
        if bcm is not None:
            bc_dict = bcm.to_dict() if hasattr(bcm, 'to_dict') else {}
            ep_ideas = bc_dict.get('total_ideas', 0)
            top_ideas = bc_dict.get('top_ideas', [])
            ep_top_capital = top_ideas[0]['capital'] if top_ideas else 0.0
        else:
            ep_ideas = 0
            ep_top_capital = 0.0

        # Theory genealogy
        tg = getattr(pipeline, '_theory_genealogy', None)
        if tg is not None:
            tg_dict = tg.to_dict() if hasattr(tg, 'to_dict') else {}
            tg_nodes = tg_dict.get('total_nodes', 0)
            tg_roots = tg_dict.get('roots', 0)
        else:
            tg_nodes = 0
            tg_roots = 0

        # ═══════════════════════════════════════════════════════════
        # 5. Resources — compute, memory, bandwidth, storage, CROI
        # ═══════════════════════════════════════════════════════════

        ra = getattr(pipeline, '_resource_accounting', None)
        if ra is not None:
            summary = ra.cycle_summary() if hasattr(ra, 'cycle_summary') else {}
            total_compute = summary.get('total_compute_ms', 0.0)
            total_memory = summary.get('total_memory_traces', 0)
            total_bandwidth = summary.get('total_bandwidth_bytes', 0.0)
            total_storage = summary.get('total_storage_entries', 0)
        else:
            total_compute = total_memory = total_bandwidth = total_storage = 0.0

        budget_total = getattr(trace, 'budget_total_ms', 1000.0) or 1000.0
        compute_util = min(total_compute / max(budget_total, 1), 1.0)
        memory_util = min(total_memory / max(100, 1), 1.0)
        bandwidth_util = min(total_bandwidth / max(10000.0, 1), 1.0)
        storage_util = min(total_storage / max(50, 1), 1.0)

        # CROI: Cognitive Return on Investment
        # knowledge gained (yield pipeline) / resource consumed (compute + memory)
        ky_total = ky_observations + ky_theories + ky_predictions + ky_validated + ky_principles
        resource_total = total_compute + total_memory * 10.0  # weight memory traces
        croi = ky_total / max(resource_total, 1.0) * 100.0  # scale for readability

        # ═══════════════════════════════════════════════════════════
        # 6. Projects — completion, strategic alignment hierarchy
        # ═══════════════════════════════════════════════════════════

        portfolio = getattr(pipeline, '_project_portfolio', None)
        if portfolio is not None:
            projects = getattr(portfolio, 'projects', {}) or {}
            total_projects = len(projects)
            active_projects = sum(
                1 for p in projects.values()
                if (hasattr(p, 'lifecycle') and p.lifecycle in ('active', 'birth', 'stalled'))
                or (hasattr(p, 'lifecycle') and hasattr(p.lifecycle, 'value')
                    and p.lifecycle.value in ('active', 'birth', 'stalled'))
            )
            completed = sum(
                1 for p in projects.values()
                if (hasattr(p, 'lifecycle') and p.lifecycle in ('completed', 'done'))
                or (hasattr(p, 'lifecycle') and hasattr(p.lifecycle, 'value')
                    and p.lifecycle.value in ('completed', 'done'))
            )
            abandoned = sum(
                1 for p in projects.values()
                if (hasattr(p, 'lifecycle') and p.lifecycle in ('terminated', 'archived'))
                or (hasattr(p, 'lifecycle') and hasattr(p.lifecycle, 'value')
                    and p.lifecycle.value in ('terminated', 'archived'))
            )
        else:
            total_projects = active_projects = completed = abandoned = 0

        # Strategic alignment hierarchy
        sc = getattr(pipeline, '_strategic_coherence', None)
        if sc is not None and hasattr(sc, '_history') and sc._history:
            last_sc = sc._history[-1]
            if isinstance(last_sc, dict):
                sc_mp = last_sc.get('mission_projects', 0.5)
                sc_pt = last_sc.get('project_tasks', 0.5)
                sc_ta = last_sc.get('task_actions', 0.5)
                sc_overall = last_sc.get('overall', 0.5)
            else:
                sc_mp = sc_pt = sc_ta = sc_overall = 0.5
        else:
            sc_mp = sc_pt = sc_ta = sc_overall = 0.5

        # ═══════════════════════════════════════════════════════════
        # 7. Social — ecosystem niches, bridges, collaboration
        # ═══════════════════════════════════════════════════════════

        if eco is not None:
            eco_dict = eco.to_dict() if hasattr(eco, 'to_dict') else {}
            niche_count = eco_dict.get('niche_count', 0)
            exhausted_niches = eco_dict.get('exhausted', 0)
            bridge_count = eco_dict.get('bridges', 0)
            social_relations = eco_dict.get('relations', 0)
            collab_eff = eco_dict.get('collaboration_efficiency', 0.5)
        else:
            niche_count = exhausted_niches = bridge_count = social_relations = 0
            collab_eff = 0.5

        # ═══════════════════════════════════════════════════════════
        # Build Snapshot
        # ═══════════════════════════════════════════════════════════

        snap = BenchmarkSnapshot(
            cycle=cycle,
            timestamp=time.time(),
            # 1. Perception
            state_estimation_error=state_estimation_error,
            surprise_rate=surprise_rate,
            unknown_unknown_discovery_rate=uu_discovery,
            forecast_accuracy=forecast_accuracy,
            counterfactual_accuracy=counterfactual_accuracy,
            # 2. Learning
            curiosity_level=curiosity_level,
            learning_rate=learning_rate,
            compression_rate=compression_rate,
            boredom_count=boredom_count,
            exploration_ratio=exploration_ratio,
            knowledge_yield_observations=ky_observations,
            knowledge_yield_theories=ky_theories,
            knowledge_yield_predictions=ky_predictions,
            knowledge_yield_validated=ky_validated,
            knowledge_yield_principles=ky_principles,
            # 3. Identity
            identity_entropy=identity_entropy,
            identity_continuity=identity_continuity,
            relational_coherence=relational_coherence,
            mission_alignment=mission_alignment,
            project_alignment=project_alignment,
            decision_alignment=decision_alignment,
            # 4. Knowledge
            representation_age_mean=rep_age,
            representation_diversity=rep_diversity,
            retirement_rate=retirement_rate,
            bridge_density=bridge_density,
            reuse_rate=reuse_rate,
            compression_achieved=compression_achieved,
            epistemic_ideas=ep_ideas,
            epistemic_top_capital=ep_top_capital,
            theory_nodes=tg_nodes,
            theory_roots=tg_roots,
            bridge_potential_avg=bridge_potential,
            # 5. Resources
            compute_utilization=compute_util,
            memory_utilization=memory_util,
            bandwidth_utilization=bandwidth_util,
            storage_utilization=storage_util,
            croi=croi,
            # 6. Projects
            active_projects=active_projects,
            total_projects=total_projects,
            completed_projects=completed,
            abandoned_projects=abandoned,
            strategic_alignment_mission_projects=sc_mp,
            strategic_alignment_project_tasks=sc_pt,
            strategic_alignment_task_actions=sc_ta,
            mission_alignment_overall=sc_overall,
            # 7. Social
            niche_count=niche_count,
            exhausted_niches=exhausted_niches,
            bridge_count=bridge_count,
            social_relations=social_relations,
            collaboration_efficiency=collab_eff,
            # Composite scores (computed below)
        )

        # ── Compute 4-level hierarchy ──
        subscores = compute_subsystem_scores(snap)
        snap.perception_score = subscores["perception"]
        snap.learning_score = subscores["learning"]
        snap.identity_score = subscores["identity"]
        snap.knowledge_score = subscores["knowledge"]
        snap.resource_score = subscores["resources"]
        snap.project_score = subscores["projects"]
        snap.social_score = subscores["social"]

        snap.system_score = compute_system_score(subscores)

        # Mission context — extract from pipeline if available
        mission_ctx = None
        mission_mgr = getattr(pipeline, '_mission_manager', None)
        if mission_mgr is not None and hasattr(mission_mgr, 'get_context_weights'):
            mission_ctx = mission_mgr.get_context_weights()
        snap.mission_score = compute_mission_score(snap.system_score, subscores, mission_ctx)

        return snap

    # ── Report Generation ───────────────────────────────────────

    def get_report(self, baseline_path: Optional[str] = None) -> BenchmarkReport:
        """Generate a complete benchmark report on demand."""
        snapshots = self._snapshots
        now = datetime.now().isoformat()

        # Build epochs: last 10, last 50, all
        epochs = {}
        if len(snapshots) >= 10:
            epochs["last_10"] = EpochSummary(
                cycle_start=snapshots[-10].cycle,
                cycle_end=snapshots[-1].cycle,
                snapshots=snapshots[-10:],
            )
        if len(snapshots) >= 50:
            epochs["last_50"] = EpochSummary(
                cycle_start=snapshots[-50].cycle,
                cycle_end=snapshots[-1].cycle,
                snapshots=snapshots[-50:],
            )
        epochs["all"] = EpochSummary(
            cycle_start=snapshots[0].cycle if snapshots else 0,
            cycle_end=snapshots[-1].cycle if snapshots else 0,
            snapshots=list(snapshots),
        )

        # Compute trends per key metric
        trend_keys = [
            ("perception_score", "Perception Score"),
            ("learning_score", "Learning Score"),
            ("identity_score", "Identity Score"),
            ("knowledge_score", "Knowledge Score"),
            ("resource_score", "Resource Score"),
            ("project_score", "Project Score"),
            ("social_score", "Social Score"),
            ("system_score", "System Score"),
            ("mission_score", "Mission Score"),
            ("curiosity_level", "Curiosity"),
            ("learning_rate", "Learning Rate"),
            ("identity_entropy", "Identity Entropy"),
            ("forecast_accuracy", "Forecast Accuracy"),
            ("croi", "CROI"),
        ]
        trends = {}
        if snapshots:
            for attr, label in trend_keys:
                vals = [getattr(s, attr, 0.0) or 0.0 for s in snapshots]
                trends[label] = classify_trend(vals).value

        # Current scores
        current_ss = snapshots[-1].system_score if snapshots else 0.0
        current_ms = snapshots[-1].mission_score if snapshots else 0.0
        ss_trend = classify_trend(
            [s.system_score for s in snapshots]
        ).value if snapshots else "insufficient_data"

        # Baseline comparison
        baseline_cmp = None
        if baseline_path:
            baseline_cmp = self._compare_baseline(baseline_path)

        report = BenchmarkReport(
            session_id=self._session_id,
            generated_at=now,
            cycle_count=len(snapshots),
            total_duration_seconds=time.time() - self._session_start,
            epochs=epochs,
            trends=trends,
            baseline=baseline_cmp,
            current_system_score=current_ss,
            current_mission_score=current_ms,
            system_score_trend=ss_trend,
        )
        return report

    def _compare_baseline(self, baseline_path: str) -> Optional[BaselineComparison]:
        """Compare current session metrics against a saved baseline."""
        baseline = load_baseline(baseline_path)
        if baseline is None or not self._snapshots:
            return None

        current = self._snapshots[-1]
        baseline_agg = baseline.get("epoch_aggregates", {}).get("all", {})
        if not baseline_agg:
            return None

        # Compare key indicators across the new structure
        delta_keys = [
            ("perception_score", "perception", "avg_score"),
            ("learning_score", "learning", "avg_score"),
            ("identity_score", "identity", "avg_score"),
            ("knowledge_score", "knowledge", "avg_score"),
            ("resource_score", "resources", "avg_score"),
            ("project_score", "projects", "avg_score"),
            ("social_score", "social", "avg_score"),
            ("system_score", "system_score", "avg"),
            ("curiosity_level", "learning", "avg_curiosity"),
            ("learning_rate", "learning", "avg_learning_rate"),
            ("identity_entropy", "identity", "avg_entropy"),
            ("forecast_accuracy", "perception", "avg_forecast_accuracy"),
            ("croi", "resources", "avg_croi"),
        ]

        deltas = {}
        improvements = []
        regressions = []

        for metric_name, category, key in delta_keys:
            cur_val = getattr(current, metric_name, 0.0) or 0.0
            base_val = baseline_agg.get(category, {}).get(key, None)
            if base_val is not None and base_val != 0:
                delta = cur_val - base_val
                deltas[metric_name] = round(delta, 4)
                # Inversion: for identity_entropy, down is good
                inversion = metric_name == "identity_entropy"
                if (delta > 0 and not inversion) or (delta < 0 and inversion):
                    improvements.append(metric_name)
                elif delta != 0:
                    regressions.append(metric_name)

        return BaselineComparison(
            baseline_label=baseline.get("session_id", "unknown"),
            baseline_time=baseline.get("generated_at", "unknown"),
            deltas=deltas,
            improvements=improvements,
            regressions=regressions,
        )

    # ── Persistence ─────────────────────────────────────────────

    def save_baseline(self, path: str) -> None:
        """Save current state as baseline for future comparisons."""
        report = self.get_report()
        save_baseline(report, path)
        self._baseline_path = path

    def save_snapshot_data(self, path: Optional[str] = None) -> str:
        """Persist all snapshot data to JSON for offline analysis."""
        path = path or os.path.join(self.output_dir, f"{self._session_id}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "session_id": self._session_id,
            "session_start": self._session_start,
            "total_cycles": len(self._snapshots),
            "snapshots": [s.to_dict() for s in self._snapshots],
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Benchmark snapshots saved to {path} ({len(self._snapshots)} cycles)")
        return path

    def load_snapshot_data(self, path: str) -> int:
        """Load previously saved snapshot data for continued analysis."""
        if not os.path.exists(path):
            logger.warning(f"No snapshot data found at {path}")
            return 0
        with open(path, 'r') as f:
            data = json.load(f)
        loaded = 0
        for sd in data.get("snapshots", []):
            try:
                snapshot = self._dict_to_snapshot(sd)
                if snapshot:
                    self._snapshots.append(snapshot)
                    loaded += 1
            except Exception as e:
                logger.warning(f"Failed to load snapshot: {e}")
                continue
        logger.info(f"Loaded {loaded} snapshots from {path}")
        return loaded

    def _dict_to_snapshot(self, sd: Dict) -> Optional[BenchmarkSnapshot]:
        """Convert a serialized dict back to a BenchmarkSnapshot."""
        try:
            # Navigate the nested dict structure
            perception = sd.get("perception", {})
            learning = sd.get("learning", {})
            identity = sd.get("identity", {})
            knowledge = sd.get("knowledge", {})
            resources = sd.get("resources", {})
            projects = sd.get("projects", {})
            social = sd.get("social", {})
            hierarchy = sd.get("hierarchy", {})

            yield_data = learning.get("knowledge_yield", {})
            eco = knowledge.get("representation_ecology", {})
            epi = knowledge.get("epistemic_capital", {})
            theory = knowledge.get("theory_genealogy", {})
            propagation = identity.get("propagation", {})
            alignment = projects.get("strategic_alignment", {})

            snap = BenchmarkSnapshot(
                cycle=sd["cycle"],
                timestamp=sd["timestamp"],
                # 1. Perception
                state_estimation_error=perception.get("state_estimation_error", 0.0),
                surprise_rate=perception.get("surprise_rate", 0.0),
                unknown_unknown_discovery_rate=perception.get("unknown_unknown_discovery_rate", 0.0),
                forecast_accuracy=perception.get("forecast_accuracy", 0.5),
                counterfactual_accuracy=perception.get("counterfactual_accuracy", 0.5),
                # 2. Learning
                curiosity_level=learning.get("curiosity_level", 0.5),
                learning_rate=learning.get("learning_rate", 0.0),
                compression_rate=learning.get("compression_rate", 0.5),
                boredom_count=learning.get("boredom_count", 0),
                exploration_ratio=learning.get("exploration_ratio", 0.5),
                knowledge_yield_observations=yield_data.get("observations", 0),
                knowledge_yield_theories=yield_data.get("theories", 0),
                knowledge_yield_predictions=yield_data.get("predictions", 0),
                knowledge_yield_validated=yield_data.get("validated", 0),
                knowledge_yield_principles=yield_data.get("principles", 0),
                # 3. Identity
                identity_entropy=identity.get("identity_entropy", 0.0),
                identity_continuity=identity.get("identity_continuity", 0.5),
                relational_coherence=identity.get("relational_coherence", 1.0),
                mission_alignment=propagation.get("mission_alignment", 0.5),
                project_alignment=propagation.get("project_alignment", 0.5),
                decision_alignment=propagation.get("decision_alignment", 0.5),
                # 4. Knowledge
                representation_age_mean=eco.get("mean_age", 0.0),
                representation_diversity=eco.get("diversity", 0.0),
                retirement_rate=eco.get("retirement_rate", 0.0),
                bridge_density=eco.get("bridge_density", 0.0),
                reuse_rate=eco.get("reuse_rate", 0.0),
                compression_achieved=eco.get("compression_achieved", 0.5),
                epistemic_ideas=epi.get("total_ideas", 0),
                epistemic_top_capital=epi.get("top_capital", 0.0),
                theory_nodes=theory.get("nodes", 0),
                theory_roots=theory.get("roots", 0),
                bridge_potential_avg=knowledge.get("bridge_potential_avg", 0.0),
                # 5. Resources
                compute_utilization=resources.get("compute_utilization", 0.5),
                memory_utilization=resources.get("memory_utilization", 0.5),
                bandwidth_utilization=resources.get("bandwidth_utilization", 0.5),
                storage_utilization=resources.get("storage_utilization", 0.5),
                croi=resources.get("croi", 0.0),
                # 6. Projects
                active_projects=projects.get("active_projects", 0),
                total_projects=projects.get("total_projects", 0),
                completed_projects=projects.get("completed_projects", 0),
                abandoned_projects=projects.get("abandoned_projects", 0),
                strategic_alignment_mission_projects=alignment.get("mission_projects", 0.5),
                strategic_alignment_project_tasks=alignment.get("project_tasks", 0.5),
                strategic_alignment_task_actions=alignment.get("task_actions", 0.5),
                mission_alignment_overall=alignment.get("overall", 0.5),
                # 7. Social
                niche_count=social.get("niche_count", 0),
                exhausted_niches=social.get("exhausted_niches", 0),
                bridge_count=social.get("bridge_count", 0),
                social_relations=social.get("relations", 0),
                collaboration_efficiency=social.get("collaboration_efficiency", 0.5),
            )
            # Compute scores
            subscores = compute_subsystem_scores(snap)
            snap.perception_score = subscores["perception"]
            snap.learning_score = subscores["learning"]
            snap.identity_score = subscores["identity"]
            snap.knowledge_score = subscores["knowledge"]
            snap.resource_score = subscores["resources"]
            snap.project_score = subscores["projects"]
            snap.social_score = subscores["social"]
            snap.system_score = compute_system_score(subscores)
            snap.mission_score = compute_mission_score(snap.system_score, subscores, None)
            return snap
        except Exception as e:
            logger.warning(f"Failed to reconstruct snapshot: {e}")
            return None

    def _auto_persist(self) -> None:
        """Auto-save to disk every 100 cycles."""
        if len(self._snapshots) > 0 and len(self._snapshots) % 100 == 0:
            self.save_snapshot_data()

    # ── Utility ─────────────────────────────────────────────────

    def clear(self) -> None:
        self._snapshots.clear()
        self._session_start = time.time()

    @property
    def cycle_count(self) -> int:
        return len(self._snapshots)

    def latest_snapshot(self) -> Optional[BenchmarkSnapshot]:
        return self._snapshots[-1] if self._snapshots else None


# ═══════════════════════════════════════════════════════════════════
# Backward Compatibility
# ═══════════════════════════════════════════════════════════════════

def compute_health_score(snapshot: BenchmarkSnapshot) -> float:
    """Legacy alias — delegates to system_score (Level 3).

    Previously computed a weighted harmonic mean; now returns the
    hierarchical system_score for backward API compatibility.
    """
    return snapshot.system_score
