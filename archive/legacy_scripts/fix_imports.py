import os

replacements = {
    "from telos_gridworld_simulator import": "from telos.examples.gridworld.simulator import",
    "from telos.examples.chess.simulator import": "from telos.examples.chess.simulator import",
    "from telos.examples.chess.env import": "from telos.examples.chess.env import",
}

for root, dirs, files in os.walk("tests"):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            with open(path, "r") as f:
                content = f.read()
            new_content = content
            for old, new in replacements.items():
                new_content = new_content.replace(old, new)
            if new_content != content:
                with open(path, "w") as f:
                    f.write(new_content)
                print(f"Updated {path}")
