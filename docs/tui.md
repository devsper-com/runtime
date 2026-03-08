# Terminal UI (TUI)

The Hivemind TUI is a terminal interface for running the swarm and inspecting runs. Launch it with:

```bash
hivemind tui
```

(Or run `hivemind` with no subcommand.)

## Layout

### Main screen

- **Branding** — Title line: “Hivemind — Distributed AI Swarm Runtime.”
- **Prompt box** — Single-line (or multi-line) input for the task. Placeholder suggests a sample task.
- **Action hints** — Short reminder of keybindings (Esc, Enter, r, o, q).
- **Output container** — Large scrollable area showing “Response” and the last run’s result. While a run is in progress, a loading state and step status (e.g. “Planning…”, “Step 2 of 5: …”) are shown.

The layout is output-first: one main view with prompt at top and most of the space for the response.

### Dashboard (key `d`)

Pressing **`d`** opens the **Dashboard** screen with six panels:

- **Tasks** — Lists tasks from the last run: task id, status (e.g. pending, running, completed), runtime, worker.
- **Swarm graph** — Represents the task DAG / swarm structure from the last scheduler state (live view of the run).
- **Memory** — Shows recent memory entries from the default store (loaded when the dashboard opens). Supports optional namespace filter (e.g. research_memory, coding_memory).
- **Activity feed** — Chronological feed of agent actions: task started/completed, tool calls, from the event log.
- **Knowledge graph** — Entities and relationships built from memory (documents, concepts, datasets, methods; edges). Built on demand when the dashboard opens.
- **Logs** — Event log content from the current run’s events folder (and optional log path).

**Leaving the dashboard:** Press **Esc** or **q** to return to the main (prompt + output) screen.

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| **Enter** | Run swarm with the current prompt (if not empty). |
| **r** | Run swarm (same as Enter when prompt has focus). |
| **d** | Open Dashboard (tasks, swarm graph, memory, logs). |
| **Esc** | Unfocus input so **r** / **q** work from the main screen; or close Dashboard and go back. |
| **o** | Focus the output area. |
| **q** | Quit the app (or go back from Dashboard). |

**Tip:** If a key doesn’t work, focus may be in the prompt input; press **Esc** to move focus out, then **r** or **q**.

## Running a task

1. Type your task in the prompt box (e.g. “Summarize swarm intelligence in one paragraph”).
2. Press **Enter** or **r**.
3. A spinner and step status (e.g. “Planning…”, “Executing step 1 of 5…”) appear while the swarm runs.
4. When the run finishes, the response area shows the aggregated result (e.g. last task result or combined result).
5. Open the Dashboard with **d** to see tasks, swarm graph, memory, and logs from this run.

Events are written to the configured events directory (e.g. `.hivemind/events`), so you can also inspect or replay runs from the CLI or scripts.
