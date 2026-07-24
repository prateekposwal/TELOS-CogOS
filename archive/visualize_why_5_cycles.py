import matplotlib.pyplot as plt
import matplotlib.patches as patches

def draw_why_5_cycles():
    fig, ax = plt.subplots(figsize=(8, 12))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 14)
    ax.axis('off')

    steps = [
        "Counterfactual Simulation",
        "Constraint Pruning",
        "Lower Branching",
        "Higher Certainty",
        "5 Cycles to Goal"
    ]

    y_pos = 12
    for i, step in enumerate(steps):
        # Draw box
        color = "lightgreen" if i == 4 else "lightgrey"
        rect = patches.FancyBboxPatch((2, y_pos), 6, 1.2, boxstyle="round,pad=0.1", ec="black", fc=color, alpha=0.8)
        ax.add_patch(rect)
        ax.text(5, y_pos + 0.6, step, ha="center", va="center", fontsize=12, fontweight='bold')
        
        # Draw arrow
        if i < len(steps) - 1:
            ax.arrow(5, y_pos, 0, -0.8, head_width=0.3, head_length=0.3, fc='black', ec='black')
        
        y_pos -= 1.8

    plt.title("Why TELOS Reached Goal in 5 Cycles", fontsize=16, fontweight='bold')
    plt.savefig("why_5_cycles.png")
    print("Graph saved as why_5_cycles.png")

if __name__ == "__main__":
    draw_why_5_cycles()
