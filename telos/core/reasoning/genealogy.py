"""Theory Genealogy — every theory has parents. Newton -> Einstein -> Quantum Gravity."""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

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
        ancestors = []
        current = self._nodes.get(node_id)
        while current and current.parent_id:
            parent = self._nodes.get(current.parent_id)
            if parent:
                ancestors.append(parent)
                current = parent
            else:
                break
        return ancestors

    def get_descendants(self, node_id: str) -> List[GenealogyNode]:
        result = []
        def walk(nid):
            node = self._nodes.get(nid)
            if node:
                for cid in node.children:
                    child = self._nodes.get(cid)
                    if child:
                        result.append(child)
                        walk(cid)
        walk(node_id)
        return result

    def to_dict(self) -> dict:
        return {
            "total_nodes": len(self._nodes),
            "roots": len([n for n in self._nodes.values() if n.parent_id is None]),
        }
