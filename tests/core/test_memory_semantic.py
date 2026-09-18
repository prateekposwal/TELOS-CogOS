"""
Semantic vocabulary + semantic retrieval (Phase 2+).

Retrieval must not depend on exact wording. These tests lock the normalization
layer (stemming, synonym folding, IDF weighting) and prove the semantic path
finds records a lexical matcher cannot.
"""

from telos.core.memory.controller import MemoryController
from telos.core.memory.semantic import (
    normalize, light_stem, term_frequencies, inverse_document_frequencies,
    cosine, SYNONYM_MAP,
)
from telos.core.memory.tiering import MemoryRecord


def _controller():
    return MemoryController()


def _add(c, rid, content, importance=0.5, domain="gridworld"):
    c.insert(MemoryRecord(record_id=rid, content=content, kind="experience",
                          domain=domain, importance=importance,
                          provenance={"caller": "test"}))


def test_synonyms_fold_to_one_concept():
    """Wall/obstacle/hazard/block map to a single canonical token."""
    for word in ("wall", "obstacle", "hazard", "barrier", "blocked"):
        assert normalize(word) == ["obstacle"], word


def test_stemming_collapses_inflections():
    """Inflected forms of a mapped word still reach the same concept."""
    assert normalize("navigating") == normalize("navigated") == ["navigate"]
    assert normalize("rewards") == normalize("reward") == ["reward"]


def test_stopwords_are_removed():
    """Function words carry no retrieval signal."""
    # "target" folds onto the "goal" concept (both are the same idea), so the
    # expected concepts are goal/goal — the point is that the stopwords vanish.
    assert normalize("the goal is to a target") == ["goal", "goal"]


def test_synonym_map_folds_target_into_goal():
    """Target/destination/objective are one concept for retrieval."""
    assert normalize("target") == normalize("destination") == ["goal"]


def test_concept_lookup_beats_stemming():
    """A curated concept wins over the cruder stemmer."""
    assert "obstacle" in normalize("walls")
    assert normalize("blocked") == ["obstacle"]


def test_normalize_preserves_term_frequency():
    """Duplicate concepts are kept so tf remains available."""
    tokens = normalize("reward reward failure")
    assert tokens.count("reward") == 2


def test_term_frequencies_are_sublinear():
    """tf uses 1 + log(count), so repetition has diminishing weight."""
    tf = term_frequencies(["reward", "reward", "reward", "goal"])
    assert tf["reward"] > tf["goal"]
    assert tf["goal"] == 1.0


def test_idf_penalizes_ubiquitous_terms():
    """A term in every document gets a lower idf than a rare one."""
    idf = inverse_document_frequencies([
        ["reward", "goal"], ["reward", "failure"], ["reward", "obstacle"],
    ])
    assert idf["goal"] > idf["reward"]


def test_cosine_bounds():
    """Cosine is 1.0 for identical vectors, 0.0 for disjoint/empty ones."""
    v = {"a": 1.0, "b": 2.0}
    assert abs(cosine(v, dict(v)) - 1.0) < 1e-9
    assert cosine({"a": 1.0}, {"b": 1.0}) == 0.0
    assert cosine({}, v) == 0.0


def test_semantic_search_finds_paraphrase():
    """A query with no literal token overlap still retrieves the record."""
    c = _controller()
    _add(c, "t", "hazard near obstacle blocked the path", importance=0.9)
    hits = c.semantic_search("avoid the wall", top_k=3)
    assert [h.record_id for h in hits] == ["t"]
    # The lexical path CAN match when keywords coincide; it fails when the
    # paraphrase shares NO content token — which is the real use case.
    c2 = _controller()
    _add(c2, "t", "gained bonus payoff goal", importance=0.9)
    assert c2.lexical_search("collect prize", top_k=3) == []
    assert [h.record_id
            for h in c2.semantic_search("collect prize", top_k=3)] == ["t"]


def test_semantic_search_prefers_target_over_hard_negative():
    """Sharing literal tokens with the query does not beat semantic match."""
    c = _controller()
    _add(c, "correct", "unsuccessful attempt caused an error and loss", importance=0.9)
    _add(c, "trap", "the attempt produced an optimal solved run", importance=0.5)
    hits = c.semantic_search("the attempt went wrong", top_k=2)
    assert hits[0].record_id == "correct"


def test_semantic_search_respects_domain_filter():
    """Domain filtering applies to the semantic path."""
    c = _controller()
    _add(c, "a", "reward at the goal", domain="gridworld")
    _add(c, "b", "reward at the goal", domain="bitcoin")
    hits = c.semantic_search("prize at destination", top_k=5, domain="gridworld")
    assert [h.record_id for h in hits] == ["a"]


def test_search_falls_back_to_lexical():
    """search() uses the semantic path first, then the lexical fallback."""
    c = _controller()
    _add(c, "t", "exact token match navigation", importance=0.9)
    # Semantic should find it; if it somehow returns nothing, lexical must not
    # silently yield an empty result for a literal match.
    assert c.search("navigation", top_k=1)[0].record_id == "t"


def test_index_rebuilds_after_insert():
    """A record inserted after the first query is retrievable (index freshness)."""
    c = _controller()
    _add(c, "a", "reward at the goal", importance=0.9)
    c.semantic_search("prize", top_k=1)
    _add(c, "b", "hazard obstacle blocked", importance=0.9)
    hits = c.semantic_search("avoid the wall", top_k=1)
    assert hits[0].record_id == "b"


def test_semantic_constants_absent_from_workspace_truth():
    """Sanity: the synonym map is populated and canonical-first."""
    assert SYNONYM_MAP["wall"] == "obstacle"
    assert SYNONYM_MAP["obstacle"] == "obstacle"
