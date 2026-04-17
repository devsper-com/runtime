"""
Coding agent — plan → implement → review using the Python API.

Equivalent to: devsper run examples/code.devsper --input task="..."
but driven entirely from Python with post-processing of results.

Install: pip install devsper
Run:     python examples/coding_agent.py
"""

import devsper

TASK = "implement a thread-safe LRU cache in Rust with get, put, and len methods"

wf = devsper.load_workflow("examples/code.devsper")
results = devsper.run_workflow(wf)

plan = next((v for k, v in results.items() if "plan" in k.lower()), "")
impl = next((v for k, v in results.items() if "implement" in k.lower()), "")
review = next((v for k, v in results.items() if "review" in k.lower()), "")

print("## Plan\n", plan)
print("\n## Implementation\n", impl)
print("\n## Review\n", review)
