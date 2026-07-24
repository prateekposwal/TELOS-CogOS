# Legacy Scripts — Archived

These 19 root-level `telos_*.py` scripts were domain experiments written before the package architecture was established. They are archived here because:

1. They import from outdated module paths that no longer exist
2. They test domain-specific behaviors (CFR, RTE, market env, etc.) that should live in domain plugins, not the root
3. They pollute the workspace root directory

## Restoration

If any script is needed, update its imports to use the `telos` package:

```python
# Old (broken):
from core.runtime import TelosV14Pipeline

# New:
from telos.core.runtime import TelosV14Pipeline
```

## Contents

| File | Domain | Status |
|------|--------|--------|
| telos_book_mirror.py | Book-market mirroring | Archived |
| telos_cfr.py | Counterfactual Regret Minimization | Archived |
| telos_coherence.py | Coherence metrics | Archived |
| telos_controller.py | Controller interface | Archived |
| telos_decision_ledger.py | Decision ledger experiments | Archived |
| telos_env.py | Environment wrapper | Archived |
| telos_feedback.py | Feedback mechanisms | Archived |
| telos_hierarchical_game.py | Hierarchical game theory | Archived |
| telos_influence.py | Influence tracking | Archived |
| telos_intent_ir.py | Intent IR experiment | Archived |
| telos_market_env.py | Market environment simulation | Archived |
| telos_negative_search.py | Negative search algorithms | Archived |
| telos_progressive_compute.py | Progressive compute experiments | Archived |
| telos_representation_memory.py | Representation memory | Archived |
| telos_rte.py | Runtime environment experiments | Archived |
| telos_safety.py | Safety constraints | Archived |
| telos_temporal_grounding.py | Temporal grounding | Archived |
| telos_trajectory.py | Trajectory tracking | Archived |
| telos_v15_semantics.py | v15 semantic experiments | Archived |
