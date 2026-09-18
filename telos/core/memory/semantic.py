"""
Semantic vocabulary — deterministic, model-free text normalization (Phase 2+).

PATTERN (retrieval must not depend on exact wording): the first memory layer
scored retrieval by literal token overlap, so a query "avoid the wall" could not
find a record stored as "hazard near obstacle" — same meaning, no shared token.
That is fine for a fixture and useless in practice.

This module gives the controller a small, explicit, offline semantic layer:

  1. normalization  — lowercase, strip punctuation, light Porter-ish stemming,
                      so "navigating"/"navigate"/"navigation" collapse to one
                      token;
  2. concept mapping — a curated lexicon folds domain synonyms onto a canonical
                      concept token ("obstacle", "wall", "barrier" -> "obstacle");
  3. idf weighting   — a corpus statistic, so rare/discriminative terms count
                      more than ubiquitous ones.

Deliberately NOT an embedding model: no network, no weights, fully deterministic
and auditable. This is honest lexical semantics, not learned semantics — a real
embedding index is a larger, separate step (and is called out as such).
"""

from __future__ import annotations

import math
import re
from typing import Dict, Iterable, List, Mapping, Sequence, Set, Tuple

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Canonical concepts: every synonym folds onto the first (canonical) token.
# Hand-curated for TELOS's decision vocabulary; extending it is a data edit,
# not a code change.
_SYNONYM_GROUPS: Tuple[Tuple[str, ...], ...] = (
    # navigation / movement
    ("navigate", "navigation", "navigating", "navigated", "navigates",
     "travel", "travels", "travelled", "traveled", "move", "moves", "motion",
     "route", "routes", "path", "paths", "trajectory", "go", "proceed",
     "advance"),
    ("goal", "target", "destination", "objective", "aim", "endpoint"),
    ("position", "location", "place", "coordinate", "cell", "spot"),
    ("corner", "edge", "extremity", "perimeter"),
    # obstacles / hazard
    ("obstacle", "wall", "barrier", "block", "blocked", "blockage", "hazard",
     "danger", "collision", "impassable"),
    ("avoid", "avoidance", "dodge", "evade", "circumvent", "bypass", "skirt"),
    # reward / success
    ("reward", "prize", "bonus", "payoff", "gain", "collect", "collection",
     "harvest", "acquire"),
    ("success", "succeed", "successful", "win", "winning", "solved", "solve",
     "achieved", "accomplish", "complete", "completed", "optimal", "good"),
    ("failure", "fail", "failed", "error", "fault", "unsuccessful", "broken",
     "loss", "lose", "lost", "regression"),
    # reasoning / decision
    ("decision", "decide", "choice", "choose", "select", "selection", "pick"),
    ("plan", "planning", "strategy", "strategic", "policy", "schedule"),
    ("hypothesis", "theory", "belief", "assumption", "conjecture"),
    ("evidence", "proof", "observation", "witness", "support"),
    ("memory", "recall", "recollection", "memory", "remember", "retrieve"),
    ("outcome", "result", "consequence", "effect", "product"),
    # uncertainty / risk
    ("uncertain", "uncertainty", "ambiguous", "unknown", "unclear", "doubt",
     "risk", "risky", "threat", "peril"),
    # governance
    ("block", "veto", "suppress", "deny", "denied", "forbid", "prohibit",
     "governance", "gate", "firewall", "stop", "halt", "cease", "prevent"),
    ("recovery", "recover", "escape", "escape_hatch", "heal", "repair"),
    # bitcoin / block-space domain vocabulary
    ("fee", "fees", "feerate", "feerate", "price", "cost", "rate"),
    ("block", "block_space", "blockspace", "block_size", "space"),
    ("mempool", "queue", "backlog", "pending", "unconfirmed"),
    ("lightning", "channel", "ln", "offchain", "layer2"),
    ("hashrate", "hashpower", "hash_rate", "mining"),
)


def _build_synonym_map() -> Dict[str, str]:
    """Build token -> canonical-concept mapping from the groups.

    Returns:
        Dict mapping every synonym onto its group's canonical token.
    """
    out: Dict[str, str] = {}
    for group in _SYNONYM_GROUPS:
        canonical = group[0]
        for word in group:
            out[word] = canonical
    return out


SYNONYM_MAP: Dict[str, str] = _build_synonym_map()

# Stopwords: tokens that carry no discriminative signal.
STOPWORDS: frozenset = frozenset({
    "the", "a", "an", "at", "in", "on", "of", "to", "for", "and", "or", "is",
    "was", "were", "be", "been", "it", "its", "this", "that", "with", "as",
    "by", "from", "into", "near", "next", "after", "before", "up", "down",
    "has", "have", "had", "not", "no", "but", "if", "then", "than", "so",
})


def light_stem(token: str) -> str:
    """Apply a conservative suffix-stripping stem.

    Only strips endings that are safe for this vocabulary ("-ing", "-ed",
    "-s"/"-es", "-tion"), and never shortens below 3 characters, so it does not
    over-conflate distinct terms (a classic stemming risk).

    Args:
        token: the raw token.

    Returns:
        The stemmed token.
    """
    if len(token) <= 4:
        return token
    for suffix, min_len in (("ations", 5), ("ation", 5), ("ings", 5),
                            ("ing", 5), ("ies", 4), ("ers", 4), ("ed", 4),
                            ("es", 4), ("s", 4)):
        if token.endswith(suffix) and len(token) - len(suffix) >= min_len - len(suffix) + 1:
            if token.endswith(suffix) and len(token) > len(suffix) + 2:
                return token[: -len(suffix)]
    return token


def normalize(text: str) -> List[str]:
    """Tokenize, stopword-filter, map to canonical concepts, then stem.

    Concept lookup is attempted on the raw token FIRST (so the curated lexicon
    wins over the cruder stemmer), then on the stem; unmapped tokens keep their
    stem.

    Args:
        text: the raw text.

    Returns:
        List of normalized concept tokens (order preserved, duplicates kept so
        term frequency remains available).
    """
    tokens: List[str] = []
    for raw in _TOKEN_RE.findall((text or "").lower()):
        if raw in STOPWORDS:
            continue
        concept = SYNONYM_MAP.get(raw)
        if concept is None:
            stem = light_stem(raw)
            concept = SYNONYM_MAP.get(stem, stem)
        if concept:
            tokens.append(concept)
    return tokens


def term_frequencies(tokens: Iterable[str]) -> Dict[str, float]:
    """Sublinear term frequencies (1 + log tf).

    Args:
        tokens: the token list.

    Returns:
        Dict token -> sublinear frequency.
    """
    counts: Dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    return {t: 1.0 + math.log(c) for t, c in counts.items()}


def inverse_document_frequencies(docs: Sequence[Sequence[str]]) -> Dict[str, float]:
    """Smoothed IDF over a document collection.

    Args:
        docs: the collection of token lists.

    Returns:
        Dict token -> idf value (>= 0).
    """
    n = max(1, len(docs))
    df: Dict[str, int] = {}
    for tokens in docs:
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1
    return {t: math.log((1.0 + n) / (1.0 + c)) + 1.0 for t, c in df.items()}


def cosine(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    """Cosine similarity between two sparse weighted vectors.

    Args:
        a: first weight vector.
        b: second weight vector.

    Returns:
        Cosine similarity in [0, 1] (0.0 when either vector is empty).
    """
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    dot = sum(w * b.get(t, 0.0) for t, w in a.items())
    if dot <= 0.0:
        return 0.0
    na = math.sqrt(sum(w * w for w in a.values()))
    nb = math.sqrt(sum(w * w for w in b.values()))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (na * nb)


__all__ = [
    "normalize", "light_stem", "term_frequencies", "inverse_document_frequencies",
    "cosine", "SYNONYM_MAP", "STOPWORDS",
]
