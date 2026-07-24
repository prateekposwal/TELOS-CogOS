"""
Visualizer: Generates performance graphs for TELOS v15 Market Benchmark.
"""
import logging
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from telos_market_env import MarketBenchmarkEnv
from telos_controller import TelosController

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('telos_plots')

def generate_plots():
    env = MarketBenchmarkEnv()
    controller = TelosController()
    state = env.reset()
    
    prices = []
    healths = []
    rewards = []
    
    for _ in range(50):
        decision = controller.think(state)
        action = decision["action"] if decision["action"] is not None else np.random.randn(6)
        state, reward, done, _ = env.step(action)
        
        prices.append(env.price)
        healths.append(decision["health"])
        rewards.append(reward)
        
        if done: break
            
    fig, axes = plt.subplots(3, 1, figsize=(10, 12))
    
    axes[0].plot(prices, label="Market Price")
    axes[0].set_title("Market Price Trend")
    axes[0].legend()
    
    axes[1].plot(healths, label="System Health", color='green')
    axes[1].set_title("Reasoning Health Trend")
    axes[1].legend()
    
    axes[2].bar(range(len(rewards)), rewards, label="Reward per Step", color='orange')
    axes[2].set_title("Reward Distribution")
    axes[2].legend()
    
    plt.tight_layout()
    plt.savefig('market_benchmark_plots.png')
    logger.info("Plots saved to 'market_benchmark_plots.png'")

if __name__ == "__main__":
    try:
        generate_plots()
    except ImportError:
        logger.error("matplotlib is required to generate plots. Install it with 'pip install matplotlib'.")
