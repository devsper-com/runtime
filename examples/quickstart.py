"""
Quickstart — run a .devsper workflow from Python.

Install: pip install devsper
Run:     python examples/quickstart.py
"""

import devsper

results = devsper.run(
    "examples/research.devsper",
    inputs={"topic": "transformer attention mechanisms"},
)

for node_id, output in results.items():
    print(f"[{node_id}]\n{output}\n")
