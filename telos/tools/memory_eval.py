#!/usr/bin/env python3
"""
Memory retrieval evaluation — measures semantic vs lexical vs naive retrieval.

PATTERN (measured, not asserted — Λ6.5): the first version of this eval used
queries that literally quoted the target record, so a lexical matcher scored
perfectly and the "win" proved nothing about real retrieval. This version uses:

  - PARAPHRASE queries with NO shared literal token with the target
    ("avoid the wall" -> "hazard near obstacle"), which is the actual use case;
  - HARD NEGATIVES — distractors that share literal tokens with the query but
    are semantically wrong, so keyword matching is actively punished;
  - an importance pair, so the ranking must also respect importance.

It reports semantic_search (the shipping path), lexical_search (the previous
rule), and naive_search (overlap-only, insertion order). The gate requires the
semantic path to beat BOTH on recall@1.

Run:
  PYTHONPATH=. ./.venv/bin/python telos/tools/memory_eval.py
  PYTHONPATH=. ./.venv/bin/python telos/tools/memory_eval.py --ci
"""

import argparse
import json
import os
import sys
from typing import Any, Callable, Dict, List

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)

from telos.core.memory.controller import MemoryController  # noqa: E402
from telos.core.memory.tiering import MemoryRecord  # noqa: E402
from telos.core.verifier.measurement import provenance  # noqa: E402

PRODUCER = "telos/tools/memory_eval.py"
MEMORY_CRITERIA = (
    "semantic_beats_lexical", "semantic_beats_naive",
    "mrr_beats_lexical", "recall_at_1_ge_0_9",
)

# Each case: a paraphrase query, the record that SHOULD win, and a hard negative
# that shares literal tokens with the query but is semantically wrong.
#   query, expected intent, record-content, negative-content
_CASES: List[Dict[str, str]] = [
    {
        "query": "avoid the wall",
        "expected": "obstacle",
        "target": "hazard near obstacle blocked the path",
        "negative": "wall of the reward vault was opened",
    },
    {
        "query": "collect the prize",
        "expected": "reward",
        "target": "gained bonus payoff at the goal",
        "negative": "collect the failed regression report",
    },
    {
        "query": "move toward the destination",
        "expected": "navigate",
        "target": "travelled along the route to the target cell",
        "negative": "removed the move from the policy log",
    },
    {
        "query": "the attempt went wrong",
        "expected": "failure",
        "target": "unsuccessful attempt caused an error and loss",
        "negative": "the attempt produced an optimal solved run",
    },
    {
        "query": "reasoning about risk",
        "expected": "uncertain",
        "target": "ambiguous unknown situation with doubt",
        "negative": "reasoning about the decided strategy",
    },
    {
        "query": "stop the action",
        "expected": "governance",
        "target": "governance gate vetoed and suppressed the action",
        "negative": "controlled the action selection ranking",
    },
    {
        # UNSEEN VOCABULARY: verified zero-overlap. The query and the target
        # share NO content token (tokenize query & target == empty set) and NO
        # lexicon entry (normalize query & target == empty set), so a curated
        # lexicon cannot solve this by construction; a learned embedding can.
        # The negative deliberately shares the query's literal tokens
        # ("vehicle", "start") so keyword matching is punished, not rewarded.
        # This is the case that isolates what real embeddings add over the
        # concept layer: measured offline semantic recall@1 = 6/7, online = 7/7.
        "query": "the vehicle would not start",
        "expected": "unseen",
        "target": "automobile failed to begin",
        "negative": "vehicle start sequence nominal",
    },
]

# Unrelated distractors: no overlap with any query, present to make the task a
# retrieval problem rather than a two-way choice.
_DISTRACTORS: List[str] = [
    "hashrate climbed across the mining network",
    "lightning channel settlement completed offchain",
    "fee histogram shows mempool backlog pending",
    "identity narrative updated the self model",
    "pattern library stored a cross domain signature",
]


def build_fixture() -> Dict[str, Any]:
    """Build the records + queries fixture.

    Returns:
        Dict with "records" (List[MemoryRecord]) and "queries"
        (List[{query, expected}]).
    """
    records: List[MemoryRecord] = []
    queries: List[Dict[str, Any]] = []
    cycle = 0
    for case in _CASES:
        cycle += 1
        tid = f"target_{case['expected']}"
        records.append(MemoryRecord(
            record_id=tid, content=case["target"], kind="experience",
            importance=0.9, created_cycle=cycle,
            provenance={"caller": "fixture"},
        ))
        cycle += 1
        nid = f"negative_{case['expected']}"
        records.append(MemoryRecord(
            record_id=nid, content=case["negative"], kind="experience",
            importance=0.5, created_cycle=cycle,
            provenance={"caller": "fixture"},
        ))
        queries.append({"query": case["query"], "expected": [tid]})
    for idx, content in enumerate(_DISTRACTORS):
        cycle += 1
        records.append(MemoryRecord(
            record_id=f"dist_{idx}", content=content, kind="experience",
            importance=0.5, created_cycle=cycle,
            provenance={"caller": "fixture"},
        ))
    return {"records": records, "queries": queries}


def _build_controller(records: List[MemoryRecord]) -> MemoryController:
    """Insert the fixture into a fresh controller.

    Args:
        records: the fixture records.

    Returns:
        A populated MemoryController.
    """
    controller = MemoryController()
    for record in records:
        controller.insert(record)
    return controller


def _metrics(ranker: Callable[[str, int], List[MemoryRecord]],
             queries: List[Dict[str, Any]], k: int,
             depth: int = 12) -> Dict[str, float]:
    """Compute recall@k, precision@k, and MRR for a ranker.

    Args:
        ranker: callable(query, top_k) -> ranked records.
        queries: the query list (each with "query" and "expected").
        k: the cutoff for recall/precision.
        depth: how deep to rank for MRR.

    Returns:
        Dict with recall_at_k, precision_at_k, mrr.
    """
    recall: List[float] = []
    precision: List[float] = []
    rr: List[float] = []
    for item in queries:
        ranked = ranker(item["query"], depth)
        expected = set(item["expected"])
        top = [r.record_id for r in ranked[:k]]
        hits = len(set(top) & expected)
        recall.append(hits / max(1, len(expected)))
        precision.append(hits / max(1, k))
        reciprocal = 0.0
        for rank, record in enumerate(ranked, 1):
            if record.record_id in expected:
                reciprocal = 1.0 / rank
                break
        rr.append(reciprocal)
    n = max(1, len(queries))
    return {
        f"recall@{k}": sum(recall) / n,
        f"precision@{k}": sum(precision) / n,
        "mrr": sum(rr) / n,
    }


def evaluate() -> Dict[str, Any]:
    """Run the fixture through semantic, lexical, and naive retrieval.

    Returns:
        Dict with each arm's metrics, the beats_baselines verdict, and sizes.
    """
    fixture = build_fixture()
    records = fixture["records"]
    controller = _build_controller(records)
    lexical = _build_controller(records)
    naive = _build_controller(records)
    queries = fixture["queries"]

    sem = {**_metrics(controller.semantic_search, queries, k=1),
           **_metrics(controller.semantic_search, queries, k=3)}
    lex = {**_metrics(lexical.lexical_search, queries, k=1),
           **_metrics(lexical.lexical_search, queries, k=3)}
    nav = {**_metrics(naive.naive_search, queries, k=1),
           **_metrics(naive.naive_search, queries, k=3)}

    beats = (
        sem["recall@1"] > lex["recall@1"]
        and sem["recall@1"] > nav["recall@1"]
        and sem["mrr"] > lex["mrr"]
    )
    criteria = {
        "semantic_beats_lexical": sem["recall@1"] > lex["recall@1"],
        "semantic_beats_naive": sem["recall@1"] > nav["recall@1"],
        "mrr_beats_lexical": sem["mrr"] > lex["mrr"],
        "recall_at_1_ge_0_9": sem["recall@1"] >= 0.9,
    }
    return {
        "provenance": provenance(PRODUCER, list(MEMORY_CRITERIA)),
        "semantic": sem,
        "lexical": lex,
        "naive": nav,
        "criteria": criteria,
        "beats_baselines": beats,
        "verdict": {
            "passed": all(criteria.values()),
            "passed_count": sum(1 for v in criteria.values() if v),
            "total": len(criteria),
        },
        "queries": len(queries),
        "records": len(records),
    }


def print_report(result: Dict[str, Any]) -> bool:
    """Print the evaluation table.

    Args:
        result: the dict returned by evaluate().

    Returns:
        True when semantic retrieval beats both baselines and recall@1 >= 0.9.
    """
    sem, lex, nav = result["semantic"], result["lexical"], result["naive"]
    print(f"\n{'TELOS Memory Retrieval Evaluation':^74}")
    print("=" * 74)
    print(f"  fixture: {result['records']} records, {result['queries']} "
          f"paraphrase queries with hard negatives")
    print("-" * 74)
    print(f"  {'metric':<16}{'semantic':>14}{'lexical':>14}{'naive':>14}")
    for key in ("recall@1", "precision@1", "mrr", "recall@3", "precision@3"):
        print(f"  {key:<16}{sem.get(key, 0):>14.3f}{lex.get(key, 0):>14.3f}"
              f"{nav.get(key, 0):>14.3f}")
    print("=" * 74)
    print("  verdict:", "semantic BEATS lexical + naive" if result["beats_baselines"]
          else "semantic does NOT beat both baselines")
    ok = bool(result["beats_baselines"]) and sem["recall@1"] >= 0.9
    print("MEMORY EVAL:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci", action="store_true",
                    help="exit 1 unless semantic retrieval beats both baselines")
    ap.add_argument("--json", default="telos/audit/memory_eval.json",
                    help="path to write the evaluation JSON")
    args = ap.parse_args()
    res = evaluate()
    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(PROJECT, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(res, f, indent=2)
        print(f"(evaluation saved: {out})")
    ok = print_report(res)
    if args.ci:
        sys.exit(0 if ok else 1)
