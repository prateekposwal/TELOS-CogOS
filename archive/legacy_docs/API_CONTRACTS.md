# TELOS v15: API Contracts & Interface Specifications

This document defines the interface contracts for the core TELOS modules. Changes to these contracts require an audit of the simulation pipeline.

## 1. Simulation Engine (`MissionSimulationEngine`)
### Input
- `mission_vector`: `np.ndarray` (shape: `state_dim`)
- `state_dim`: `int` (default: 6)
- `semantic_engine`: `Optional[SemanticExpansionEngine]`

### Key Methods
- `generate_worlds(current_state, n_worlds, horizon)`: Returns `List[CounterfactualWorld]`
- `register_potential_roles(entity_id, roles)`: Registers entity manifolds

## 2. Pipeline (`TelosV14Pipeline`)
### Configuration (`PipelineConfig`)
- `mission_vector`: `Optional[np.ndarray]`
- `simulation_strategy`: `SimulationStrategy`
- `compute_budget_ms`: `float`

### Execution (`execute`)
- **Input**: `current_state: np.ndarray`, `context: Optional[Dict]`
- **Output**: `PipelineResult` (Contains `selected_trajectory`, `health_score`, `safety_passed`, etc.)

## 3. Semantic Engine (`SemanticExpansionEngine`)
### Methods
- `expand(entity_id, potential_roles, mission_vector, context_vector, progressive_tier, constraints)`: Returns `EntityManifold`
- `update_historical_weight(role_id, success)`: Updates role prior probability

## 4. Feedback Loop (`EpistemicFeedbackLoop`)
### Methods
- `record_outcome(trajectory_steps, health, drift, corruption, success, trajectory_id, active_role_ids, metadata)`: Stores outcome and triggers calibration.
