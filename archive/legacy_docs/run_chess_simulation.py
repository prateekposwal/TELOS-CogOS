import time
import numpy as np
from telos.examples.chess.env import ChessEnv, TELOSChessAdapter
from telos.core.runtime import PipelineConfig, TelosV14Pipeline

def run_simulation(duration_sec=60):
    env = ChessEnv()
    adapter = TELOSChessAdapter(env)
    config = PipelineConfig(adapter=adapter, n_worlds=5, horizon=2, use_safety_gate=False, state_dim=6)
    pipeline = TelosV14Pipeline(config)
    
    state = env.reset()
    start_time = time.time()
    
    metrics = {"steps": 0, "successful_moves": 0, "illegal_moves": 0}
    
    print(f"Starting 60-second chess simulation with random agent...")
    
    while time.time() - start_time < duration_sec:
        result = pipeline.execute(state)
        if result.selected_trajectory:
            print(f"Trajectory found! steps: {len(result.selected_trajectory.steps)}")
        else:
            print("No trajectory found.")
        # Using the last step of the trajectory to make a move in the environment
        if result.selected_trajectory and result.selected_trajectory.steps:
            action = result.selected_trajectory.steps[-1].action
            obs, reward, done, info = env.step(action)
            
            metrics["steps"] += 1
            if info.get('illegal', False):
                metrics["illegal_moves"] += 1
            else:
                metrics["successful_moves"] += 1
                state = obs
                
            if done:
                state = env.reset()
        else:
            # If no trajectory, just pass or reset
            time.sleep(0.1)

    print(f"\n--- Simulation Results ({duration_sec}s) ---")
    print(f"Total Steps: {metrics['steps']}")
    print(f"Successful Moves: {metrics['successful_moves']}")
    print(f"Illegal Moves: {metrics['illegal_moves']}")
    print(f"Success Rate: {(metrics['successful_moves']/max(1, metrics['steps']))*100:.2f}%")

if __name__ == "__main__":
    run_simulation()
