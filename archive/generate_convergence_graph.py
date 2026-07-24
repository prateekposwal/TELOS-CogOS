import matplotlib.pyplot as plt
import matplotlib.patches as patches

def draw_why_graph():
    fig, ax = plt.subplots(figsize=(7, 9))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis('off')

    data = [
        "Counterfactual simulation",
        "Constraint pruning",
        "Lower branching",
        "Higher certainty",
        "5 cycles to goal"
    ]

    y_pos = 8
    for i, text in enumerate(data):
        # Box
        color = "#A8DADC" if i < len(data) - 1 else "#E63946"
        rect = patches.FancyBboxPatch((2, y_pos), 6, 1, boxstyle="round,pad=0.2", ec="#1D3557", fc=color)
        ax.add_patch(rect)
        ax.text(5, y_pos + 0.5, text, ha="center", va="center", fontsize=12, fontweight='bold', color="#1D3557")
        
        # Arrow
        if i < len(data) - 1:
            ax.arrow(5, y_pos, 0, -0.6, head_width=0.3, head_length=0.3, fc='#1D3557', ec='#1D3557')
        
        y_pos -= 1.6

    plt.title("Mechanism of Efficiency: TELOS Convergence", fontsize=14, fontweight='bold')
    plt.savefig("telos_convergence.png")
    print("Graph saved as telos_convergence.png")

if __name__ == "__main__":
    draw_why_graph()
