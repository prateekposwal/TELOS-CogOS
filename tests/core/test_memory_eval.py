"""
Memory retrieval evaluation — the measured proof the memory layer works.

The eval must (a) run deterministically, (b) show the SEMANTIC path beating both
the lexical and naive baselines on paraphrase queries with hard negatives, and
(c) fail if the semantic layer is swapped out (a regression guard against a
rigged fixture).
"""

from telos.core.memory.controller import MemoryController
from telos.tools.memory_eval import (
    build_fixture, evaluate, _build_controller, _metrics,
)


def test_fixture_is_well_formed():
    """The fixture has paraphrase queries, expected targets, and hard negatives."""
    fixture = build_fixture()
    assert fixture["queries"]
    assert len(fixture["records"]) > len(fixture["queries"]) * 2
    for item in fixture["queries"]:
        assert item["expected"]


def test_fixture_queries_do_not_quote_their_targets():
    """Regression: queries must be paraphrases, not verbatim copies.

    The original fixture quoted the target record, so a lexical matcher scored
    1.0 and the win proved nothing. Here, no query shares its FULL wording with
    the target, and at least one shares no literal token at all — which is
    enough to break pure lexical matching.
    """
    fixture = build_fixture()
    by_id = {r.record_id: r for r in fixture["records"]}
    no_overlap = 0
    for item in fixture["queries"]:
        target = by_id[item["expected"][0]].content.lower()
        q_tokens = set(item["query"].lower().split())
        if not any(t in target for t in q_tokens):
            no_overlap += 1
        # Never the whole query verbatim inside the target.
        assert item["query"].lower() not in target
    assert no_overlap >= 1, "at least one query must share no literal token"


def test_evaluate_passes():
    """Semantic retrieval beats lexical and naive, with recall@1 >= 0.9."""
    result = evaluate()
    assert result["beats_baselines"] is True
    assert result["semantic"]["recall@1"] >= 0.9
    assert result["semantic"]["recall@1"] > result["lexical"]["recall@1"]
    assert result["semantic"]["mrr"] > result["lexical"]["mrr"]


def test_evaluate_is_deterministic():
    """Two evaluations over the fixture are identical."""
    assert evaluate() == evaluate()


def test_semantic_beats_lexical_when_werordered():
    """If semantic ranking is reduced to lexical, the measured advantage drops.

    Locks the eval against a fixture that would pass trivially.
    """
    fixture = build_fixture()
    controller = _build_controller(fixture["records"])
    lexical = _build_controller(fixture["records"])
    sem = _metrics(controller.semantic_search, fixture["queries"], k=1)
    lex = _metrics(lexical.lexical_search, fixture["queries"], k=1)
    assert sem["recall@1"] > lex["recall@1"]
    assert lex["recall@1"] < 0.9


def test_metrics_are_bounded():
    """Recall/precision/MRR stay within [0, 1] for every arm."""
    result = evaluate()
    for section in ("semantic", "lexical", "naive"):
        for key, value in result[section].items():
            assert 0.0 <= value <= 1.0, (section, key, value)
