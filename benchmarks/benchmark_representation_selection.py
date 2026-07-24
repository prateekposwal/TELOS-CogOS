import time
import numpy as np
from telos.core.simulation import CounterfactualEngine
from telos.examples.synthetic.simulator import SyntheticWorld
from telos.core.planner import RepresentationPlanner
from telos.world.world import World

def benchmark_runtimes(n_episodes=10, noise_std=0.05):
    simulator = SyntheticWorld(noise_std=noise_std)
    engine = CounterfactualEngine(simulator)
    
    # Define Runtimes
    # Baseline A, Baseline B, and TELOS (Adaptive)
    # We simulate this by varying the RepresentationPlanner's 'enabled' state
    # and the available RepresentationTransform set.
    
    results = {"BaselineA": [], "BaselineB": [], "TELOS": []}
    
    for runtime in results.keys():
        print(f"Benchmarking {runtime}...")
        total_utility = 0
        switches = 0
        
        for _ in range(n_episodes):
            state = simulator.initial_state()
            episode_utility = 0
            
            # Simplified Decision Loop
            for step in range(20):
                # Simulate decisions based on "runtime" mode
                if runtime == "TELOS":
                    # Adaptive Logic (Pseudo-code for the experiment)
                    # In a real run, this uses RepresentationPlanner
                    action = np.array([0.1, 0.0]) 
                else:
                    action = np.array([0.1, 0.0])
                    
                state = simulator.transition(state, action)
                facts = simulator.get_facts(state)
                # Utility is negative distance from origin (simple example)
                episode_utility -= facts.metrics["distance_from_origin"]
            
            results[runtime].append(episode_utility)
            
    # Reporting
    print(f"\n--- Benchmark Report (Noise: {noise_std}) ---")
    for runtime, utilities in results.items():
        print(f"{runtime:<12} | Avg Utility: {np.mean(utilities):.4f}")

if __name__ == "__main__":
    benchmark_runtimes()
