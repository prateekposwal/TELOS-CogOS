"""
StructuralCausalModel — Implements Pearl's do-calculus for causal reasoning.

Provides do() interventions and counterfactual queries that the
CounterfactualEngine uses instead of random perturbation.

Axiom 4.3 (Possibility Preservation) is strengthened by causal:
  - do(action) breaks incoming edges to the action variable
  - Generated counterfactuals are structural, not merely statistical
"""

import logging
import numpy as np
from collections import defaultdict, deque
from typing import Dict, List, Any, Optional, Callable, Tuple

logger = logging.getLogger("telos_scm")


class StructuralCausalModel:
    """Structural Causal Model implementing Pearl's do-calculus.

    The SCM maintains:
      - A causal graph: variable → list of (cause, equation_or_None)
      - Structural equations: variable → callable that computes value from causes
      - Domain facts parser: builds graph from observed domain facts

    The CounterfactualEngine uses this model to:
      1. do(action) — set a variable by intervention, breaking incoming edges
      2. counterfactual(evidence, intervention) — compute P(Y | do(X=x), evidence=e)
      3. Store causal_graph in the decision trace
    """

    def __init__(self):
        self.causal_graph: Dict[str, List[Tuple[str, Optional[Callable]]]] = {}
        """variable → list of (cause, equation_or_None)"""
        self.structural_equations: Dict[str, Callable] = {}
        """variable → function that computes value from causes"""
        self._variable_values: Dict[str, Any] = {}
        """Current values of all variables in the graph"""
        self._intervention_history: List[Dict] = []
        """Tracks all do() interventions applied"""

    def add_edge(self, cause: str, effect: str,
                 equation: Optional[Callable] = None) -> None:
        """Define causal relationship: cause → effect.

        If equation is provided, it defines how the effect is computed
        from its causes. Otherwise, the relationship is structural but
        the functional form is unknown (requires simulation).

        Args:
            cause: The causal variable name
            effect: The affected variable name
            equation: Optional function that maps cause values → effect value
        """
        if effect not in self.causal_graph:
            self.causal_graph[effect] = []
        self.causal_graph[effect].append((cause, equation))
        if equation is not None:
            self.structural_equations[effect] = equation
        logger.debug(f"SCM: edge {cause} → {effect}")

    def set_value(self, variable: str, value: Any) -> None:
        """Set the current value of a variable in the model."""
        self._variable_values[variable] = value

    def get_value(self, variable: str) -> Any:
        """Get the current value of a variable."""
        return self._variable_values.get(variable)

    def do(self, variable: str, value: Any) -> Dict[str, Any]:
        """Intervene: set variable to value, breaking incoming edges.

        Implements the do-operator from Pearl's causal calculus:
          do(X=x) replaces the structural equation for X with X=x,
          breaking all incoming causal edges to X.

        Returns the resulting world state after intervention.

        Args:
            variable: The variable to intervene on
            value: The value to set (can be any type)

        Returns:
            Dict of variable → value after intervention
        """
        # Record the intervention
        intervention_record = {
            "variable": variable,
            "value": value,
            "type": "do",
        }
        self._intervention_history.append(intervention_record)

        # Set the intervened value, which breaks incoming edges
        self._variable_values[variable] = value

        # Propagate through the causal graph in topological order (Kahn's
        # algorithm): a descendant is recomputed only after its causal
        # parents have settled, so equations see consistent inputs.
        descendants = self._find_descendants(variable)
        for desc in self._topological_order(descendants):
            if desc in self.structural_equations:
                try:
                    causes = self._get_cause_values(desc)
                    new_val = self.structural_equations[desc](causes)
                    self._variable_values[desc] = new_val
                except Exception as e:
                    logger.warning(
                        f"SCM: failed to propagate to {desc}: {e}"
                    )

        logger.debug(f"SCM: do({variable}={value}) — propagated to {len(descendants)} descendants")
        return dict(self._variable_values)

    def _topological_order(self, descendants: List[str]) -> List[str]:
        """Kahn's algorithm on the induced descendant subgraph.

        Returns a topologically sorted list of the descendant nodes
        (causes before effects). If the subgraph contains a cycle the
        remaining nodes are emitted after the acyclic prefix so
        propagation always terminates.
        """
        if not descendants:
            return []
        dset = set(descendants)
        # Induced subgraph: effect -> [causes that are also descendants]
        subgraph: Dict[str, List[str]] = {}
        for effect, causes in self.causal_graph.items():
            if effect in dset:
                subgraph[effect] = [c[0] for c in causes if c[0] in dset]

        in_degree = {n: len(subgraph.get(n, [])) for n in descendants}
        reverse: Dict[str, List[str]] = defaultdict(list)
        for effect, causes in subgraph.items():
            for cause in causes:
                reverse[cause].append(effect)

        queue = deque(n for n in descendants if in_degree[n] == 0)
        order: List[str] = []
        while queue:
            n = queue.popleft()
            order.append(n)
            for effect in reverse.get(n, []):
                in_degree[effect] -= 1
                if in_degree[effect] == 0:
                    queue.append(effect)

        # Cycle remainder (never hangs; emitted after the acyclic prefix)
        order.extend(n for n in descendants if n not in order)
        return order

    def _find_descendants(self, variable: str) -> List[str]:
        """Find all descendants of a variable in the causal graph."""
        descendants = []
        visited = set()
        queue = [variable]
        while queue:
            current = queue.pop(0)
            for effect, causes in self.causal_graph.items():
                cause_names = [c[0] for c in causes]
                if current in cause_names and effect not in visited:
                    visited.add(effect)
                    descendants.append(effect)
                    queue.append(effect)
        return descendants

    def _get_cause_values(self, variable: str) -> Dict[str, Any]:
        """Get current values of all causes of a variable."""
        causes = self.causal_graph.get(variable, [])
        return {c[0]: self._variable_values.get(c[0]) for c in causes}

    def counterfactual(self, evidence: Dict[str, Any],
                       intervention: Dict[str, Any]) -> Dict[str, Any]:
        """Compute counterfactual: P(Y | do(X=x), evidence=e).

        Three-step abduction-action-prediction process:
          1. Abduction: Update beliefs given evidence
          2. Action: Apply do(intervention)
          3. Prediction: Compute resulting world state

        Args:
            evidence: Observed variable → value pairs
            intervention: Variable → value for the do() operation

        Returns:
            Counterfactual world state as variable → value dict
        """
        # Save current state
        saved_values = dict(self._variable_values)

        try:
            # Step 1: Abduction — incorporate evidence
            for var, val in evidence.items():
                self._variable_values[var] = val

            # Step 2: Action — apply do(intervention)
            result_state = dict(self._variable_values)
            for var, val in intervention.items():
                result_state = self.do(var, val)

            # Step 3: Prediction is the state after do() with evidence
            return result_state

        finally:
            # Restore original state
            self._variable_values = saved_values

    def parse_domain_facts(self, facts: Any) -> None:
        """Parse domain facts to build a causal graph.

        Recognizes common causal patterns:
          - position → next_position (movement causality)
          - action → state_change (action effect)
          - terrain → cost (environmental causality)

        Args:
            facts: DomainFacts object from the pipeline
        """
        if facts is None:
            return

        # Extract constraints and resources to infer causal structure
        if hasattr(facts, "constraints"):
            for c in facts.constraints:
                if "→" in str(c):
                    parts = str(c).split("→")
                    cause = parts[0].strip()
                    effect = parts[1].strip()
                    self.add_edge(cause, effect)

        if hasattr(facts, "resources"):
            for key, val in facts.resources.items():
                if isinstance(val, (int, float)):
                    self._variable_values[key] = val
                elif hasattr(val, "tolist"):
                    self._variable_values[key] = val.tolist()
                else:
                    self._variable_values[key] = val

        # ── Fix 5b: Parse causal_edges from metadata ──
        if hasattr(facts, "metadata") and facts.metadata:
            causal_edges = facts.metadata.get("causal_edges", [])
            for edge_str in causal_edges:
                if "→" in edge_str:
                    parts = edge_str.split("→")
                    cause = parts[0].strip()
                    effect = parts[1].strip()
                    self.add_edge(cause, effect)
                    logger.debug(f"SCM: added causal edge from metadata: {cause} → {effect}")

        # Add standard causal edges for movement domains
        if "position" in self._variable_values:
            self.add_edge("position", "next_position")

        if "action" in self._variable_values:
            self.add_edge("action", "state_change")

        if "terrain" in self._variable_values:
            self.add_edge("terrain", "cost")

        logger.debug(
            "SCM: parsed domain facts — {} edges, {} variables".format(
                len(self.causal_graph), len(self._variable_values)
            )
        )

    def generate_counterfactual_worlds(
        self,
        base_state: np.ndarray,
        actions: List[Any],
        n_worlds: int = 3,
    ) -> List[Dict[str, Any]]:
        """Generate counterfactual worlds by do(action) interventions.

        Instead of random perturbation (the old approach), this uses
        structural causal do() operations to produce grounded alternatives.

        Args:
            base_state: Current world state
            actions: List of candidate actions to intervene with
            n_worlds: Number of worlds to generate per action

        Returns:
            List of counterfactual world states
        """
        worlds = []

        # Seed causal values from the base state
        self._variable_values["position"] = base_state.tolist() if hasattr(base_state, "tolist") else base_state

        for action in actions[:max(1, n_worlds)]:
            # do(action) — structural intervention
            action_name = str(action) if not isinstance(action, str) else action
            self._variable_values["action"] = action_name
            world = self.do("action", action_name)
            worlds.append(world)

            # Generate variants by do() on action with different params
            for i in range(max(1, n_worlds // len(actions)) - 1):
                variant_action = f"{action_name}_variant_{i}"
                world_var = self.do("action", variant_action)
                worlds.append(world_var)

        return worlds[:n_worlds]

    @property
    def graph_summary(self) -> Dict[str, Any]:
        """Summary of the causal graph for decision trace logging."""
        return {
            "edges": [
                f"{cause} → {effect}"
                for effect, causes in self.causal_graph.items()
                for cause, _ in causes
            ],
            "variables": list(self._variable_values.keys()),
            "interventions": len(self._intervention_history),
            "has_structural_equations": len(self.structural_equations) > 0,
        }

    def graph_edit_distance(self, other: 'StructuralCausalModel') -> float:
        """🟢 NEW #5: Compute ΔW = graph edit distance between two SCM states.
        
        Measures structural divergence between current and previous causal graph.
        ΔW = |E_t Δ E_{t+1}| / max(|E_t|, |E_{t+1}|, 1) + Σ|V_t[k] - V_{t+1}[k]| / ...
        
        Returns:
            Normalized distance in [0, 1]
        """
        if not other:
            return 0.0
        # Edge difference
        e1 = set(self.graph_summary.get("edges", []))
        e2 = set(other.graph_summary.get("edges", []))
        edge_diff = len(e1.symmetric_difference(e2))
        max_edge = max(len(e1), len(e2), 1)
        # Variable value difference
        v1, v2 = self._variable_values, other._variable_values
        all_keys = set(list(v1.keys()) + list(v2.keys()))
        val_diffs = 0
        for k in all_keys:
            if k in v1 and k in v2:
                if str(v1[k]) != str(v2[k]):
                    val_diffs += 1
            else:
                val_diffs += 1
        max_vals = max(len(all_keys), 1)
        # Normalized sum
        return (edge_diff / max_edge + val_diffs / max_vals) / 2.0

    def reset(self) -> None:
        """Reset the SCM to initial state."""
        self.causal_graph.clear()
        self.structural_equations.clear()
        self._variable_values.clear()
        self._intervention_history.clear()
