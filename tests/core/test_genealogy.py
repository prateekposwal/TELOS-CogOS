"""Tests for TheoryGenealogy — lineage/descendant walks with cycle guards."""

import pytest

from telos.core.reasoning.genealogy import TheoryGenealogy


def _make_cycle_genealogy():
    """A, B with parent_id pointing at each other (corrupt cycle)."""
    tg = TheoryGenealogy()
    a = tg.register("A", cycle=0)
    b = tg.register("B", parent_id=a, cycle=1)
    # Corrupt: create a cycle A <-> B
    tg._nodes[a].parent_id = b
    return tg, a, b


class TestGenealogyGuards:
    def test_lineage_terminates_on_cycle(self):
        tg, a, b = _make_cycle_genealogy()
        lineage = tg.get_lineage(a)
        # Must terminate (no infinite loop); B is the only ancestor reachable
        assert len(lineage) == 1
        assert lineage[0].name == "B"

    def test_lineage_cycle_other_direction(self):
        tg, a, b = _make_cycle_genealogy()
        lineage = tg.get_lineage(b)
        assert len(lineage) == 1
        assert lineage[0].name == "A"

    def test_lineage_normal_chain(self):
        tg = TheoryGenealogy()
        n = tg.register("Newton", cycle=0)
        e = tg.register("Einstein", parent_id=n, cycle=1)
        q = tg.register("QuantumGravity", parent_id=e, cycle=2)
        lineage = tg.get_lineage(q)
        assert [x.name for x in lineage] == ["Einstein", "Newton"]

    def test_descendants_terminate_on_cycle(self):
        tg = TheoryGenealogy()
        a = tg.register("A", cycle=0)
        b = tg.register("B", parent_id=a, cycle=1)
        c = tg.register("C", parent_id=b, cycle=2)
        # Corrupt: C's child B forms a cycle B -> C -> B
        tg._nodes[b].children.append(c)
        tg._nodes[c].children.append(b)
        desc = tg.get_descendants(a)
        names = [x.name for x in desc]
        assert names == ["B", "C"]  # each visited once
        assert len(names) == len(set(names))

    def test_descendants_shared_child_visited_once(self):
        tg = TheoryGenealogy()
        root = tg.register("Root", cycle=0)
        left = tg.register("Left", parent_id=root, cycle=1)
        right = tg.register("Right", parent_id=root, cycle=2)
        shared = tg.register("Shared", parent_id=left, cycle=3)
        tg._nodes[right].children.append(shared)  # shared child of both
        desc = tg.get_descendants(root)
        names = [x.name for x in desc]
        assert names.count("Shared") == 1

    def test_regression_infinite_loop_fixed(self):
        """The pre-fix get_lineage hung forever on a parent cycle (probe-confirmed)."""
        import signal

        tg = TheoryGenealogy()
        a = tg.register("A", cycle=0)
        b = tg.register("B", parent_id=a, cycle=1)
        tg._nodes[a].parent_id = b  # cycle

        def _handler(signum, frame):
            raise TimeoutError("get_lineage infinite loop")

        signal.signal(signal.SIGALRM, _handler)
        signal.setitimer(signal.ITIMER_REAL, 2.0)
        try:
            tg.get_lineage(a)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
