"""Theory Genealogy — every theory has parents. Newton -> Einstein -> Quantum Gravity."""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

logger = logging.getLogger('telos_genealogy')


@dataclass
class GenealogyNode:
    id: str
    name: str
    parent_id: Optional[str] = None
    birth_cycle: int = 0
    children: List[str] = field(default_factory=list)


class TheoryGenealogy:
    """Tracks ancestry and descent of theories."""

    def __init__(self):
        self._nodes: Dict[str, GenealogyNode] = {}
        self._count: int = 0

    def register(self, name: str, parent_id: Optional[str] = None,
                 cycle: int = 0) -> str:
        nid = f"theory_{int(time.time() * 1000)}_{self._count}"
        self._count += 1
        node = GenealogyNode(id=nid, name=name, parent_id=parent_id, birth_cycle=cycle)
        self._nodes[nid] = node
        if parent_id and parent_id in self._nodes:
            self._nodes[parent_id].children.append(nid)
        logger.info(f"Genealogy: registered '{name}' ({nid}) parent={parent_id}")
        return nid

    def get_lineage(self, node_id: str) -> List[GenealogyNode]:
        """Ancestor chain from node up to the root.

        Cycle-guarded: a visited set bounds the walk so a corrupt
        parent cycle can never loop forever.
        """
        ancestors = []
        seen: Set[str] = {node_id}
        current = self._nodes.get(node_id)
        while current and current.parent_id:
            if current.parent_id in seen:
                logger.warning(
                    f"Genealogy: cycle detected at '{current.parent_id}' while "
                    f"walking lineage of '{node_id}' — stopping"
                )
                break
            seen.add(current.parent_id)
            parent = self._nodes.get(current.parent_id)
            if parent:
                ancestors.append(parent)
                current = parent
            else:
                break
        return ancestors

    def get_descendants(self, node_id: str) -> List[GenealogyNode]:
        """All descendants of a node (recursive children walk).

        Visited-set guarded: shared or cyclic children are visited once.
        """
        result = []
        visited: Set[str] = set()
        def walk(nid):
            if nid in visited:
                return
            visited.add(nid)
            node = self._nodes.get(nid)
            if node:
                for cid in node.children:
                    child = self._nodes.get(cid)
                    if child and child.id not in visited:
                        result.append(child)
                        walk(cid)
        walk(node_id)
        return result

    def to_dict(self) -> dict:
        return {
            "total_nodes": len(self._nodes),
            "roots": len([n for n in self._nodes.values() if n.parent_id is None]),
        }
