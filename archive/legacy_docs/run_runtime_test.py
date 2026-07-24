import time
import numpy as np
from telos.examples.chess.env import ChessEnv, TELOSChessAdapter
from telos.core.runtime import PipelineConfig, TelosV14Pipeline

def run_runtime_stability_test(duration_sec=60, use_telos_policy=True):
    env = ChessEnv()
    adapter = TELOSChessAdapter(env)
    
    # Configure Pipeline
    config = PipelineConfig(
        adapter=adapter,
        n_worlds=10,
        horizon=4,
        use_safety_gate=True,
        rte_enabled=True,
        state_dim=6
    )
    pipeline = TelosV14Pipeline(config)
    
    state = env.reset()
    start_time = time.time()
    
    # Instrumentation Metrics
    latencies = []
    safety_pass = 0
    illegal_moves = 0
    total_cycles = 0
    worlds = []
    
    print(f"Starting Runtime Instrumentation Test ({'TELOS Policy' if use_telos_policy else 'Random Policy'})...")
    
    while time.time() - start_time < duration_sec and total_cycles < 100: # Limit cycles for stability test
        loop_start = time.time()
        total_cycles += 1
        
        # 1. Pipeline Execution
        result = pipeline.execute(state)
        
        # 2. Decision Logic
        if use_telos_policy and result.selected_trajectory:
            action = result.selected_trajectory.steps[-1].action
        else:
            action = adapter.sample_action(state, np.ones(6))
            
        # 3. Environment Step
        _, _, done, info = env.step(action)
        
        # 4. Instrument Runtime Metrics
        latencies.append(time.time() - loop_start)
        if result.safety_passed: safety_pass += 1
        if info.get('illegal', False): illegal_moves += 1
        worlds.append(result.worlds_generated)
        
        if done:
            env.reset()
            
    # Aggregate and Report
    print(f"\n--- Runtime Instrumentation Report ---")
    print(f"Policy: {'TELOS' if use_telos_policy else 'Random'}")
    print(f"Total Decision Cycles: {total_cycles}")
    print(f"Avg Pipeline Latency: {sum(latencies)/max(1, total_cycles):.4f}s")
    print(f"Safety Gate Pass Rate: {safety_pass/max(1, total_cycles):.2%}")
    print(f"Illegal Move Rate: {illegal_moves/max(1, total_cycles):.2%}")
    print(f"Avg Worlds Explored: {sum(worlds)/max(1, total_cycles):.2f}")

if __name__ == "__main__":
    # Baseline: Random Policy
    run_runtime_stability_test(duration_sec=60, use_telos_policy=False)
    # Target: TELOS Policy
    run_runtime_stability_test(duration_sec=60, use_telos_policy=True)
