import matplotlib.pyplot as plt
import matplotlib.patches as patches

def draw_pipeline():
    fig, ax = plt.subplots(figsize=(9, 11))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 14)
    ax.axis('off')

    # Data from Cycle 5 of the demo
    phases = [
        ("World Generation", "Simulated: 15 worlds"),
        ("Constraint Filtering", "Status: PASSED"),
        ("Identity Evaluation", "Decision Integrity: 1.00"),
        ("Maintenance Cost", "Budget: 19.4ms"),
        ("Counterfactual Ranking", "Best Score: 1.00"),
        ("Chosen Action", "Intent: Reflex")
    ]

    y_pos = 12
    for i, (title, data) in enumerate(phases):
        # Draw box
        rect = patches.FancyBboxPatch((2, y_pos), 6, 1.6, boxstyle="round,pad=0.2", ec="#1D3557", fc="#A8DADC", alpha=0.9)
        ax.add_patch(rect)
        
        # Text
        ax.text(5, y_pos + 1.1, title, ha="center", va="center", fontsize=12, fontweight='bold', color="#1D3557")
        ax.text(5, y_pos + 0.5, data, ha="center", va="center", fontsize=10, color="#1D3557")
        
        # Draw arrow
        if i < len(phases) - 1:
            ax.arrow(5, y_pos, 0, -1.0, head_width=0.3, head_length=0.3, fc='#1D3557', ec='#1D3557')
        
        y_pos -= 2.2

    plt.title("TELOS Cognitive Pipeline: Cycle 5 Snapshot", fontsize=16, fontweight='bold', color="#1D3557")
    plt.savefig("pipeline_flow.png")
    print("Data-rich graph saved as pipeline_flow.png")

if __name__ == "__main__":
    draw_pipeline()
