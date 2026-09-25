"""
Model-class assessment (V10) — domain-agnostic, vocabulary-free.

The frontier question: does TELOS's machinery transfer to an unseen domain whose
ontology it was NOT given? This module makes NO reference to `mediated` /
`common_cause` / `direct_delay` — it uses only generic, domain-free primitives
(correlation, lagged correlation, intervention effects, autocorrelation) to
decide what CLASS of model is even adequate:

  SUFFICIENT                    the current model class explains the evidence
  ADDITIONAL_STRUCTURE_REQUIRED an extra (unnamed) degree of freedom is needed
  UNRESOLVED                    the evidence cannot distinguish the candidates
  MODEL_CLASS_INSUFFICIENT      NO model in the assumed class can explain it

Crucially distinguishing UNRESOLVED (not yet distinguished) from
MODEL_CLASS_INSUFFICIENT (cannot be explained by the class at all) — the former
is a witness gap, the latter is a model-class failure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Set, Tuple

import numpy as np


class ModelClassVerdict(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    ADDITIONAL_STRUCTURE_REQUIRED = "ADDITIONAL_STRUCTURE_REQUIRED"
    UNRESOLVED = "UNRESOLVED"
    MODEL_CLASS_INSUFFICIENT = "MODEL_CLASS_INSUFFICIENT"


def _corr(x, y) -> float:
    if np.std(x) < 1e-9 or np.std(y) < 1e-9:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def _lag_corr(x, y, k: int) -> float:
    if len(x) <= k:
        return 0.0
    return _corr(x[:-k], y[k:])


def assess(x: np.ndarray, y: np.ndarray, *, do_xy: Optional[float] = None,
           do_yx: Optional[float] = None, intermediate: Optional[bool] = None,
           effect_threshold: float = 0.15, corr_threshold: float = 0.3,
           lag_threshold: float = 0.4) -> Dict[str, Any]:
    """Assess what model CLASS is adequate for an observed variable pair.

    Args:
        x: first series.
        y: second series.
        do_xy: interventional effect of x on y (None = not tested).
        do_yx: interventional effect of y on x (None = not tested).
        intermediate: whether an intermediate signal was observed (optional).
        effect_threshold: |effect| to count as causal.
        corr_threshold: |corr| to count as an association.
        lag_threshold: lagged |corr| to count as a delayed signal.

    Returns:
        {"verdict": ModelClassVerdict, "corr", "lag", "do_xy", "do_yx", "autocorr"}.
    """
    corr = _corr(x, y)
    lag = max(_lag_corr(x, y, k) for k in (1, 2, 3))
    autocorr = _corr(x[1:], x[:-1])
    sx = do_xy is not None and abs(do_xy) > effect_threshold
    sy = do_yx is not None and abs(do_yx) > effect_threshold

    verdict: ModelClassVerdict
    association = abs(corr) >= corr_threshold or lag >= lag_threshold
    if sx and sy:
        # BIDIRECTIONAL: the assumed acyclic class cannot express this.
        verdict = ModelClassVerdict.MODEL_CLASS_INSUFFICIENT
    elif lag >= lag_threshold and abs(corr) < corr_threshold:
        # a delayed-only association: direct-delay suffices unless an observed
        # intermediate requires an extra, unnamed degree of freedom.
        verdict = (ModelClassVerdict.ADDITIONAL_STRUCTURE_REQUIRED
                   if intermediate is True else ModelClassVerdict.SUFFICIENT)
    elif association:
        # a (mostly contemporaneous) association
        if do_xy is None and do_yx is None:
            verdict = ModelClassVerdict.UNRESOLVED          # direction unclear
        elif sx or sy:
            verdict = ModelClassVerdict.SUFFICIENT
        else:
            # association with NO observed intervention effect: a latent common
            # cause / hidden state is required (not mere noise).
            verdict = ModelClassVerdict.ADDITIONAL_STRUCTURE_REQUIRED
    else:
        # no association — noise, or a stateful system with no observable edge
        verdict = (ModelClassVerdict.MODEL_CLASS_INSUFFICIENT
                   if abs(autocorr) > 0.6 else ModelClassVerdict.UNRESOLVED)
    return {"verdict": verdict, "corr": round(corr, 3), "lag": round(lag, 3),
            "do_xy": do_xy, "do_yx": do_yx, "autocorr": round(autocorr, 3)}


# ── ModelClass contract (V11) ────────────────────────────────────────────────
#
# ONE abstraction. A model class declares the STRUCTURES it can represent and
# gives a verdict for an observation pair using the SAME `assess` primitives.
# AcyclicModel (V10 behavior, preserved) and StatefulModel are representations
# under the same discovery/planning/Evidence machinery — no new engine.

class ModelClass(ABC):
    """Contract every model class implements."""

    @abstractmethod
    def admissible_structure(self) -> Set[str]:
        """The structural vocabulary this class can represent."""
        ...

    @abstractmethod
    def admissible_verdicts(self) -> Set[str]:
        """The epistemic verdicts this class can emit."""
        ...

    @abstractmethod
    def represent(self, x: np.ndarray, y: np.ndarray, **evidence: Any) -> Dict[str, Any]:
        """Represent an observation pair: {verdict, structure, status, ...}."""
        ...

    def explain(self, result: Dict[str, Any]) -> str:
        """A short explanation of a representation result."""
        return (f"{self.__class__.__name__}: verdict={result.get('verdict')} "
                f"structure={result.get('structure')} status={result.get('status')}")

    def falsify(self, result: Dict[str, Any], contradiction: Dict[str, Any]) -> bool:
        """Whether a new observation refutes a represented structure.

        A structure is falsified when a discriminating intervention contradicts
        its required test (e.g. a feedback claim is refuted if do(cause) does not
        move the effect).
        """
        struct = result.get("structure")
        if struct == "feedback":
            dx = contradiction.get("do_xy")
            dy = contradiction.get("do_yx")
            return not (dx and abs(dx) > 0.15 and dy and abs(dy) > 0.15)
        if struct == "shared_state":
            # contradicted if a bare cause DOES move the effect (then not shared)
            dx = contradiction.get("do_xy")
            return bool(dx and abs(dx) > 0.15)
        return False


class AcyclicModel(ModelClass):
    """Acyclic (DAG) model class — the V10 behavior, PRESERVED."""

    def admissible_structure(self) -> Set[str]:
        return {"direct", "delayed"}

    def admissible_verdicts(self) -> Set[str]:
        return {v.value for v in ModelClassVerdict}

    def represent(self, x: np.ndarray, y: np.ndarray, **evidence: Any) -> Dict[str, Any]:
        r = assess(x, y, **evidence)
        return {"verdict": r["verdict"].value,
                "structure": r["verdict"].value,
                "status": "NA", "detail": r}


class StatefulModel(ModelClass):
    """Stateful / feedback model class — represents recurrence and hidden state."""

    def admissible_structure(self) -> Set[str]:
        return {"direct", "delayed", "feedback", "shared_state"}

    def admissible_verdicts(self) -> Set[str]:
        return {v.value for v in ModelClassVerdict} | {"STRUCTURE_CANDIDATE"}

    def represent(self, x: np.ndarray, y: np.ndarray, **evidence: Any) -> Dict[str, Any]:
        r = assess(x, y, **evidence)
        dx, dy = r["do_xy"], r["do_yx"]
        # MUST observe an intervention before asserting any structure — never
        # fabricate recurrence/state from association + autocorrelation alone.
        if dx is None or dy is None:
            return {"verdict": ModelClassVerdict.UNRESOLVED.value, "structure": None,
                    "status": "NA", "detail": r,
                    "required_test": "intervene on both variables to test recurrence"}
        sx = dx is not None and abs(dx) > 0.15
        sy = dy is not None and abs(dy) > 0.15

        # genuine RECURRENCE: BOTH directions move under intervention
        if sx and sy:
            return {"verdict": "STRUCTURE_CANDIDATE", "structure": "feedback",
                    "status": "UNVALIDATED", "detail": r,
                    "required_test": "intervene on both variables; confirm mutual effect"}

        # association + persistence but NO intervention effect => a SHARED HIDDEN
        # STATE, not feedback (distinguished precisely by the null interventions).
        assoc = abs(r["corr"]) >= 0.3 or r["lag"] >= 0.4
        if assoc and not sx and not sy and abs(r["autocorr"]) > 0.6:
            return {"verdict": "STRUCTURE_CANDIDATE", "structure": "shared_state",
                    "status": "UNVALIDATED", "detail": r,
                    "required_test": "do(cause) does NOT move effect => shared state"}

        # otherwise the stateful class agrees with the acyclic verdict — and the
        # V10 MODEL_CLASS_INSUFFICIENT is NOT absorbed (kept first-class).
        return {"verdict": r["verdict"].value, "structure": r["verdict"].value,
                "status": "NA", "detail": r}


# ─────────────────────────────────────────────────────────────────────────────
# V13 — Compositional causal representation (bounded).  This is a STRUCTURE
# OBJECT, not an engine: AcyclicModel/StatefulModel above operate over exactly
# the same Evidence.  Bound is a benchmark constraint, not an architectural
# claim.  representation != belief: a structure can be representable while its
# confidence stays UNRESOLVED.
# ─────────────────────────────────────────────────────────────────────────────

MAX_NODES = 5
MAX_EDGES = 8
MAX_DEPTH = 3
_EFFECT_EPS = 0.15


@dataclass(frozen=True)
class CausalRelation:
    source: str
    target: str
    kind: str                      # "direct" | "temporal" | "recurrent"
    lag: int = 1
    status: str = "CANDIDATE"      # never SUPPORTED from representation alone


@dataclass(frozen=True)
class CausalStructure:
    nodes: Tuple[str, ...]
    relations: Tuple[CausalRelation, ...] = ()
    state_variables: Tuple[str, ...] = ()
    components: Tuple[Tuple[str, ...], ...] = ()
    confidence: str = "UNRESOLVED"
    required_intervention: Optional[str] = None
    # R1: the representation envelope is bounded.  Exceeding a structural bound
    # must be EXPLICIT — never present a silently truncated graph as complete.
    #   bound_exceeded = envelope cannot express the requested structure
    #   UNRESOLVED     = envelope can express it, but evidence cannot identify it
    bound_exceeded: bool = False
    n_observed: int = 0

    @property
    def status(self) -> str:
        if self.bound_exceeded:
            return "BOUND_EXCEEDED"
        return self.confidence

    @property
    def representable(self) -> bool:
        return not self.bound_exceeded and bool(self.nodes)

    def recurrent_edges(self) -> Tuple[CausalRelation, ...]:
        return tuple(r for r in self.relations if r.kind == "recurrent")

    def temporal_edges(self) -> Tuple[CausalRelation, ...]:
        return tuple(r for r in self.relations if r.kind == "temporal")

    def recurrent_components(self) -> Tuple[Tuple[str, ...], ...]:
        return tuple(c for c in self.components if len(c) >= 2)


def _lag_strength(x: np.ndarray, y: np.ndarray, lag: int) -> float:
    x = np.asarray(x, float) - float(np.mean(x))
    y = np.asarray(y, float) - float(np.mean(y))
    a, b = x[:-lag], y[lag:]
    if a.size < 8:
        return 0.0
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
    return abs(float(np.dot(a, b) / denom))


def _best_lag(x: np.ndarray, y: np.ndarray) -> int:
    best, bl = -1.0, 1
    for lag in range(1, MAX_DEPTH + 1):
        c = _lag_strength(x, y, lag)
        if c > best:
            best, bl = c, lag
    return bl


def _delayed_lag(x: np.ndarray, y: np.ndarray, eps: float = 0.3) -> int:
    """A genuine multi-step delay: a lag>=2 with non-trivial cross-correlation
    (under mutual coupling the lag-1 peak can mask it)."""
    best, bl = eps, 0
    for lag in range(2, MAX_DEPTH + 1):
        c = _lag_strength(x, y, lag)
        if c > best:
            best, bl = c, lag
    return bl


def discover_structure(observations: Dict[str, np.ndarray],
                       interventions: Dict[Tuple[str, str], Optional[float]],
                       ) -> CausalStructure:
    """Bounded compositional structure from Evidence. No engine, no planner.

    observations: {var: series}.  interventions: {(cause, effect): effect or None}
    where None means "not yet observed" (leaves confidence UNRESOLVED).
    """
    all_nodes = tuple(sorted(observations))
    n_observed = len(all_nodes)
    missing = [f"do({a})->{b}" for a in all_nodes for b in all_nodes if a != b
               and interventions.get((a, b)) is None]

    # significant directed edges from interventions
    edges: Set[Tuple[str, str]] = set()
    for a in all_nodes:
        for b in all_nodes:
            if a != b:
                eff = interventions.get((a, b))
                if eff is not None and abs(eff) > _EFFECT_EPS:
                    edges.add((a, b))

    # R1: bounded envelope.  If the requested structure exceeds the node bound,
    # return an EXPLICIT BOUND_EXCEEDED result with NO truncated graph — never a
    # partial structure presented as complete.
    if n_observed > MAX_NODES:
        return CausalStructure(
            nodes=(), relations=(), state_variables=(), components=(),
            confidence="UNRESOLVED", required_intervention=None,
            bound_exceeded=True, n_observed=n_observed,
        )

    nodes = all_nodes

    relations: list = []
    for a, b in sorted(edges):
        if len(relations) < MAX_EDGES:
            relations.append(CausalRelation(a, b, "recurrent" if (b, a) in edges else "direct"))
    for a, b in sorted(edges):
        if len(relations) < MAX_EDGES:
            lag = _delayed_lag(observations[a], observations[b])
            if lag > 1:      # delay is recorded compositionally, alongside recurrence
                relations.append(CausalRelation(a, b, "temporal", lag=lag))

    # connected components over undirected connectivity
    adj: Dict[str, Set[str]] = {a: set() for a in nodes}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    seen: Set[str] = set()
    components: list = []
    for a in nodes:
        if a in seen or not adj[a]:
            continue
        stack, comp = [a], []
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            comp.append(u)
            stack.extend(adj[u])
        components.append(tuple(sorted(comp)))

    # recurrence = a DIRECTED CYCLE within the component (not mutual pairs only;
    # a 3-cycle v0->v1->v2->v0 has no a<->b pair but is recurrent).
    def _has_cycle(comp: Tuple[str, ...]) -> bool:
        cs = set(comp)
        sub = {(a, b) for (a, b) in edges if a in cs and b in cs}
        color = {u: 0 for u in comp}

        def dfs(u: str) -> bool:
            color[u] = 1
            for w in comp:
                if (u, w) in sub:
                    if color[w] == 1:
                        return True
                    if color[w] == 0 and dfs(w):
                        return True
            color[u] = 2
            return False

        return any(color[u] == 0 and dfs(u) for u in comp)

    recurrent_components = [c for c in components if len(c) >= 2 and _has_cycle(c)]
    connected = {x for c in components for x in c}
    state_vars = tuple(a for a in nodes
                       if not any(e[0] == a for e in edges)   # no causal output
                       and a not in connected)
    return CausalStructure(
        nodes=nodes, relations=tuple(relations), state_variables=state_vars,
        components=tuple(sorted(recurrent_components)),
        confidence="UNRESOLVED" if missing else "CANDIDATE",
        required_intervention=missing[0] if missing else None,
        bound_exceeded=False, n_observed=n_observed,
    )
