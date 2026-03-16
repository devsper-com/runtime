# Examples

Example workflows are under **`examples/`**. Run them from the **project root** so paths and `PYTHONPATH` resolve correctly. Outputs go to **`examples/output/`** unless overridden.

## Research pipeline (literature review)

**Goal:** Turn a directory of papers (PDF/DOCX) into a structured literature review (e.g. topic extraction, citation graph, swarm synthesis).

**CLI:**

```bash
devsper research papers/
devsper research .
```

**Script:**

```bash
uv run python examples/research/literature_review.py [directory]
```

**Steps:** docproc corpus pipeline → topic extraction → citation graph → swarm literature review → markdown report in `examples/output/`.

---

## Codebase analysis

**Goal:** Analyze a repository’s architecture (index, dependencies, structure, API surface) and produce a summary.

**CLI:**

```bash
devsper analyze path/to/repo
devsper analyze .
```

**Script:**

```bash
uv run python examples/coding/analyze_repository.py [path]
```

**Steps:** codebase_indexer → dependency_graph_builder → architecture_analyzer → api_surface_extractor → store in memory → swarm synthesis → markdown report.

---

## Dataset analysis

**Goal:** Profile a dataset (e.g. CSV), run basic analytics (distribution, outliers, correlation), and produce a report. Uses Iris by default if scikit-learn is available and no CSV is provided.

**Script:**

```bash
uv run python examples/data_science/dataset_analysis.py [path-to.csv]
```

**Steps:** dataset_profile → distribution/outlier/correlation tools → store in memory → swarm summary → report in `examples/output/`.

---

## Document intelligence

**Goal:** Process a directory of documents (PDF/DOCX), extract concepts, build a knowledge graph and timeline, and produce an intelligence report.

**Script:**

```bash
uv run python examples/documents/analyze_documents.py [directory]
```

**Steps:** docproc corpus pipeline → concept frequency → knowledge graph → timeline extraction → store in memory → swarm report.

---

## Experiment runner (parameter sweep)

**Goal:** Run a parameter grid (e.g. learning rate, batch size) and use the swarm experiment runner to evaluate combinations; report best configuration.

**Script:**

```bash
uv run python examples/experiments/parameter_sweep.py --params '{"lr":[0.01,0.1],"batch_size":[16,32]}'
uv run python examples/experiments/parameter_sweep.py --params '{"lr":[0.01,0.1]}' --max-combinations 10 --runs 2
```

**Steps:** grid_search_runner → swarm_experiment_runner for each combination (or sample) → report.

**Options:**

- `--params`: JSON object mapping parameter names to lists of values.
- `--max-combinations`: Cap on grid size.
- `--runs`: Runs per combination for the swarm experiment runner.

---

## Other examples

- **`examples/demo_swarm.py`** — Minimal swarm run (no tools/memory).
- **`examples/coding/generate_docs.py`** — Generate docstrings for a repo.
- **`examples/coding/refactor_candidates.py`** — Refactor candidate detection.
- **`examples/research/research_gap_analysis.py`** — Research gap analysis.
- **`examples/research/research_graph.py`** — Research graph building.
- **`examples/experiments/monte_carlo_demo.py`** — Monte Carlo experiment demo.
- **`examples/data_science/run_experiments.py`** — Run experiments pipeline.

Use **`uv run python examples/<path>/<script>.py`** from the project root, or the CLI where applicable (`devsper research`, `devsper analyze`).
