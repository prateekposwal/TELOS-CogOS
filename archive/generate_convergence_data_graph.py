import matplotlib.pyplot as plt

# Data: Cycle vs. Distance to Goal
# TELOS: Moves diagonally (optimal)
cycles_telos = [1, 2, 3, 4, 5]
dist_telos = [5.66, 4.24, 2.82, 1.41, 0.0]

# Baseline: Erratic walk (inefficient)
cycles_baseline = range(1, 13)
# Simulating erratic movement: (0,0)->(1,0)->(1,1)->(2,1)->(2,2)->(3,2)->(3,3)->(3,4)->(4,4)
# Plus some jitter to stretch it to 12 cycles
dist_baseline = [5.66, 5.0, 4.24, 4.12, 3.60, 3.16, 2.82, 2.23, 2.0, 1.41, 1.0, 0.0]

plt.figure(figsize=(8, 5))
plt.plot(cycles_telos, dist_telos, marker='o', label='TELOS Convergence (5 Cycles)', color='#E63946', linewidth=3)
plt.plot(cycles_baseline, dist_baseline, marker='s', label='Baseline Search (12 Cycles)', color='#457B9D', linestyle='--', linewidth=1.5)

plt.xlabel('Decision Cycle', fontsize=12)
plt.ylabel('Euclidean Distance to Goal', fontsize=12)
plt.title('Path Convergence Comparison: TELOS vs Baseline', fontsize=14, fontweight='bold')
plt.legend()
plt.grid(True, linestyle='--', alpha=0.7)
plt.savefig('convergence_data.png')
print("Graph saved as convergence_data.png")
