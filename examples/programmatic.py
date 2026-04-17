"""
Programmatic API — build and run workflows directly in Python without a .devsper file.

Install: pip install devsper
Run:     python examples/programmatic.py
"""

import devsper

# Define tasks as NodeSpecs — dependencies expressed by passing the parent spec.
search = devsper.NodeSpec(
    prompt="Find the 10 most relevant recent papers on: quantum error correction. "
           "Return title, authors, year, and a one-sentence summary for each.",
)

analyze = devsper.NodeSpec(
    prompt="From the search results, identify the 3 key open problems "
           "and 3 most promising research directions.",
    depends_on=[search],
)

synthesize = devsper.NodeSpec(
    prompt="Write a 400-word executive summary of the state of the art in "
           "quantum error correction, referencing the papers and insights above.",
    model="claude-opus-4-7",
    depends_on=[search, analyze],
)

results = devsper.run_specs([search, analyze, synthesize])

for node_id, output in results.items():
    print(f"[{node_id}]\n{output}\n")
