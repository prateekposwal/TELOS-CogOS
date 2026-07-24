import numpy as np
from telos.examples.chess.env import ChessEnv, TELOSChessAdapter

def run_match(max_moves=50):
    env = ChessEnv()
    adapter = TELOSChessAdapter(env)
    
    print(f"--- Starting 1-Minute Chess Match (Random Legal) ---")
    
    done = False
    move_count = 0
    
    for _ in range(max_moves):
        state = env.board.flatten().astype(np.float64) # Dummy state
        action = adapter.sample_action(state, np.zeros(6))
        obs, reward, done, info = env.step(action)
        
        move_count += 1
        if done:
            break
            
    result = "Checkmate/Draw" if done else "Max moves reached"
    print(f"Match Finished: {result}")
    print(f"Total Moves: {move_count}")
    print(f"Final Board Turn: {'White' if env.turn == 0 else 'Black'}")

if __name__ == "__main__":
    run_match()
