#!/usr/bin/env python3
"""
Memory retrieval evaluation — measures recall@k / precision@k / MRR for the
TieredMemory + MemoryController against a naive baseline.

PATTERN (measured, not asserted — Λ6.5): "memory is better now" is only true if
it retrieves the right record more often than the baseline. This harness runs a
FIXED fixture through both retrievers and reports the delta. The controller's
retrieval score is query-overlap x importance (with tier promotion); the naive
baseline is plain overlap in insertion order. If the controller does not beat
naive, the Phase-2 target is NOT met — and we say so.

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

# Fixed fixture: each query's correct record is the HIGH-importance member of a
# pair with IDENTICAL content overlap, and the low-importance member is inserted
# first. A retrievers that ignores importance (naive) picks the wrong one; a
# retriever that weights importance picks the right one.
_PAIRS = [
    ("a", "grid reward at corner", 0.2, 0.9),
    ("b", "hazard avoid route near wall", 0.25, 0.85),
    ("c", "fastest fee estimate for next block", 0.15, 0.8),
    ("d", "lightning channel close settlement", 0.3, 0.9),
    ("e", "navigate blocked wall", 0.1, 0.75),
    ("f", "collect reward corner", 0.2, 0.95),
]

_DISTRACTORS = [
    ("reward schedule chart", 0.5),
    ("fee market congestion", 0.5),
    ("channel funding transaction", 0.5),
    ("wall geometry map", 0.5),
    ("corner office", 0.5),
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
    for tag, content, low_imp, high_imp in _PAIRS:
        cycle += 1
        records.append(MemoryRecord(
            record_id=f"exp_{tag}_low", content=content, kind="experience",
            importance=low_imp, created_cycle=cycle,
            provenance={"caller": "fixture"},
        ))
        cycle += 1
        records.append(MemoryRecord(
            record_id=f"exp_{tag}_high", content=content, kind="experience",
            importance=high_imp, created_cycle=cycle,
            provenance={"caller": "fixture"},
        ))
        queries.append({"query": content, "expected": [f"exp_{tag}_high"]})
    for idx, (content, imp) in enumerate(_DISTRACTORS):
        cycle += 1
        records.append(MemoryRecord(
            record_id=f"dist_{idx}", content=content, kind="experience",
            importance=imp, created_cycle=cycle,
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
    """Run the fixture through the controller and the naive baseline.

    Returns:
        Dict with controller/naive metrics, the beats_naive verdict, and sizes.
    """
    fixture = build_fixture()
    controller = _build_controller(fixture["records"])
    naive = _build_controller(fixture["records"])
    queries = fixture["queries"]

    c1 = _metrics(controller.search, queries, k=1)
    c3 = _metrics(controller.search, queries, k=3)
    n1 = _metrics(naive.naive_search, queries, k=1)
    n3 = _metrics(naive.naive_search, queries, k=3)

    controller_metrics = {**c1, **{key: value for key, value in c3.items()
                                   if key not in c1}}
    naive_metrics = {**n1, **{key: value for key, value in n3.items()
                              if key not in n1}}
    beats = (
        controller_metrics["mrr"] > naive_metrics["mrr"]
        and controller_metrics["recall@1"] >= naive_metrics["recall@1"]
    )
    return {
        "controller": controller_metrics,
        "naive": naive_metrics,
        "beats_naive": beats,
        "queries": len(queries),
        "records": len(fixture["records"]),
    }


def print_report(result: Dict[str, Any]) -> bool:
    """Print the evaluation table.

    Args:
        result: the dict returned by evaluate().

    Returns:
        True when the controller beats naive and recall@1 >= 0.9.
    """
    c = result["controller"]
    n = result["naive"]
    print(f"\n{'TELOS Memory Retrieval Evaluation':^72}")
    print("=" * 72)
    print(f"  fixture: {result['records']} records, {result['queries']} queries")
    print("-" * 72)
    print(f"  {'metric':<18}{'controller':>14}{'naive':>14}")
    for key in ("recall@1", "precision@1", "mrr", "recall@3", "precision@3"):
        print(f"  {key:<18}{c.get(key, 0.0):>14.3f}{n.get(key, 0.0):>14.3f}")
    print("=" * 72)
    print("  verdict:", "controller BEATS naive" if result["beats_naive"]
          else "controller does NOT beat naive")
    ok = bool(result["beats_naive"]) and c["recall@1"] >= 0.9
    print("MEMORY EVAL:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci", action="store_true",
                    help="exit 1 unless the controller beats naive (recall@1 >= 0.9)")
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
