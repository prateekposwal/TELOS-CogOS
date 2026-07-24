"""
Plugin-based container for RepresentationTransforms.

Transforms register themselves by name; the RepresentationPlanner
queries the registry when building a TransformChain for a given
RuntimeState.
"""

from typing import Dict, List, Optional
from representation_transform import RepresentationTransform


class TransformRegistry:
    """Container for registered transforms.

    Acts as a plugin system: transforms can be registered from any
    module, and the planner queries all registered transforms to
    find the optimal chain.
    """

    def __init__(self):
        self._transforms: Dict[str, RepresentationTransform] = {}

    def register(self, transform: RepresentationTransform) -> None:
        """Register a transform by its `.name` property."""
        if not isinstance(transform, RepresentationTransform):
            raise TypeError(
                f"Expected RepresentationTransform, got {type(transform).__name__}"
            )
        self._transforms[transform.name] = transform

    def get(self, name: str) -> Optional[RepresentationTransform]:
        """Retrieve a transform by name."""
        return self._transforms.get(name)

    def all(self) -> List[RepresentationTransform]:
        """Return all registered transforms."""
        return list(self._transforms.values())

    def remove(self, name: str) -> None:
        """Remove a transform by name."""
        self._transforms.pop(name, None)

    def clear(self) -> None:
        """Remove all transforms."""
        self._transforms.clear()

    @property
    def count(self) -> int:
        return len(self._transforms)

    def __repr__(self) -> str:
        names = ", ".join(self._transforms.keys())
        return f"TransformRegistry({names})"
