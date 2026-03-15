---
title: Workflows
---

# Workflows

Workflows are predefined, repeatable multi-step pipelines defined in TOML. They let you codify a sequence of tasks — with dependencies, conditional branching, typed outputs, and template variables — and run them with a single command.

## Defining a Workflow

Workflow definitions live in `workflow.hivemind.toml` or inline in your project's `hivemind.toml`.

### v1.4 Format

The current format uses `[workflow.<name>]` tables with a `[[workflow.<name>.steps]]` array:

```toml
[workflow.research_report]
name = "research_report"
version = "1.0"
description = "Gather sources, analyze findings, and produce a report."

[[workflow.research_report.steps]]
id = "gather"
task = "Search for recent papers on {input.topic} and return a list of titles and URLs."
output_schema = "list[{title: str, url: str}]"

[[workflow.research_report.steps]]
id = "analyze"
task = "Read the papers from the gather step and summarize key findings: {steps.gather.result}"
depends_on = ["gather"]
output_schema = "str"

[[workflow.research_report.steps]]
id = "draft"
task = "Write a structured report using the analysis: {steps.analyze.result}"
depends_on = ["analyze"]
output_schema = "str"

[[workflow.research_report.steps]]
id = "review"
task = "Review the draft for factual accuracy: {steps.draft.result}"
depends_on = ["draft"]
if = "input.enable_review == 'true'"
output_schema = "str"
```

### Legacy Format

Older projects may use the flat `[workflow]` table. This format does not support dependencies or conditionals — steps run sequentially.

```toml
[workflow]
name = "simple_pipeline"
steps = ["fetch_data", "process_data", "generate_summary"]
```

## Step Properties

| Property        | Required | Description                                                |
|-----------------|----------|------------------------------------------------------------|
| `id`            | yes      | Unique identifier for the step                             |
| `task`          | yes      | Task description (supports template variables)             |
| `depends_on`    | no       | List of step IDs that must complete first                  |
| `output_schema` | no       | Expected output type (used for validation)                 |
| `if`            | no       | Condition expression; step is skipped when false           |

## Template Variables

Task descriptions support three template namespaces:

| Pattern                        | Resolves to                                      |
|--------------------------------|--------------------------------------------------|
| `{input.key}`                  | A value passed via `--input KEY=VALUE` at run time |
| `{steps.step_id.result}`      | The full result of a prior step                  |
| `{steps.step_id.field_name}`  | A specific field from a prior step's typed output |

## Execution Model

1. **Input validation** — required inputs (those referenced by `{input.*}` templates) are checked before execution begins.
2. **Wave scheduling** — steps are grouped into waves by dependency order. All steps in the same wave run **in parallel** via the [DAG executor](/docs/swarm_runtime).
3. **Conditional skipping** — steps with an `if` condition that evaluates to false are skipped. Any step that depends on a skipped step is also skipped.
4. **Result propagation** — each step's output is made available to downstream steps through template variables.

```text
Wave 0: [gather]
Wave 1: [analyze]
Wave 2: [draft]
Wave 3: [review]  (skipped if enable_review != 'true')
```

## Branching and Typed Outputs

Steps can declare an `output_schema` to enforce structure on their results. Downstream steps can reference individual fields, enabling branching logic where different steps consume different parts of an earlier step's output.

```toml
[[workflow.pipeline.steps]]
id = "classify"
task = "Classify the input document: {input.doc}"
output_schema = "{category: str, confidence: float}"

[[workflow.pipeline.steps]]
id = "deep_analysis"
task = "Perform deep analysis on this {steps.classify.category} document."
depends_on = ["classify"]
if = "steps.classify.confidence > 0.8"
```

## CLI Commands

### List available workflows

```bash
hivemind workflow list
```

### Validate a workflow definition

```bash
hivemind workflow validate research_report
```

### Run a workflow

```bash
hivemind workflow run research_report --input topic="diffusion models" --input enable_review=true
```

Inputs are passed as `KEY=VALUE` pairs. Multiple `--input` flags are supported.

## Next Steps

- [Swarm Runtime](/docs/swarm_runtime) — how hivemind schedules parallel task waves
- [Agents](/docs/concepts/agents) — the workers that execute each step
- [CLI Reference](/docs/cli) — full command documentation for `hivemind workflow`
