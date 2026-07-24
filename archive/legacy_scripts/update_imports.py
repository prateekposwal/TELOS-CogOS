import os

replacements = {
    "from telos.core.runtime import": "from telos.core.runtime import",
    "from telos.core.simulation import": "from telos.core.simulation import",
    "from telos.core.planner import": "from telos.core.planner import",
    "from telos.core.contracts.domain_model import": "from telos.core.contracts.domain_model import",
}

for root, dirs, files in os.walk("."):
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
