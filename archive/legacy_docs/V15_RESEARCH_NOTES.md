# TELOS v15: Research Notes - Latent Role Manifolds

## 1. Hypothesis: Overcoming Functional Fixedness
Static semantic labeling (e.g., Phone = "Communication Device") creates functional fixedness. By treating entities as **Latent Role Manifolds**—clouds of potential affordances—we hypothesize that the simulation engine will discover creative, non-obvious strategies (e.g., using a phone as a signal beacon, or a heavy object as a projectile) without explicit hardcoding.

## 2. Technical Observations (Arena Benchmarks)
- **Clipping**: Top-$K$ clipping (with $K=3$) maintains semantic resolution while keeping computational complexity $O(K \cdot N_{entities})$ manageable for real-time trajectory search.
- **Relational Affordances**: The RAG (Relational Affordance Graph) effectively unlocked a 300% increase in emergent capability discovery during simulation setup.
- **Feasibility**: The strict pruning of unfeasible roles (e.g., fragile glass as load-bearing) is essential. Without this filter, the RAG occasionally proposed "absurd" trajectories.

## 3. Prior Calibration Logic
Calibration is linked to the `DecisionLedger`. A role’s `base_weight` is adjusted by $\pm 0.1$ or $0.05$ based on the final trajectory utility ($J$). This creates a reinforcement loop where "successful" affordances are prioritized in the manifold, effectively learning "what works" in the environment.

## 4. Future Directions
- **Semantic Resolution Scaling**: Investigating a dynamic K (K = $f(\text{uncertainty})$). High uncertainty states should trigger deeper manifold expansion.
- **Cross-Sim Feedback**: Sharing learned role weights across different simulation environments to accelerate initial manifold calibration in new scenarios.
