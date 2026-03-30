"""
devsper TUI: prompt + output. Enter or r to run. Esc unfocuses input. q quit.
"""

import os
import threading

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Input

from devsper.tui.dashboard_screen import DashboardScreen
from devsper.tui.layout import devsperLayout


class devsperTUI(App[None]):
    """Main screen: prompt + output. Run shows loading then result."""

    TITLE = "devsper"
    SUB_TITLE = "Distributed AI Swarm Runtime"

    BINDINGS = [
        Binding("r", "run_swarm", "Run", show=True),
        Binding("d", "dashboard", "Dashboard", show=True),
        Binding("p", "toggle_pause", "Pause", show=True),
        Binding("i", "inject_note", "Inject", show=True),
        Binding("escape", "unfocus_input", "Unfocus input", show=True),
        Binding("o", "focus_output", "Output", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    CSS = """
    /* Compact branding */
    #branding {
        height: auto;
        padding: 0 2;
        text-align: center;
    }
    #logo-line {
        color: #6EE7B7;
        text-style: bold;
    }
    /* Prompt box — full border so box is closed */
    #prompt-box {
        border: heavy #6EE7B7;
        padding: 1 2;
        margin: 0 2 0 2;
        height: auto;
        background: #0F172A;
    }
    #prompt-input {
        border: none;
        background: transparent;
        padding: 0;
        margin: 0;
        width: 100%;
    }
    #action-hints {
        color: #64748b;
        padding: 0 2 1 2;
        text-align: center;
    }
    /* Response area — full border, takes rest of screen */
    #output-container {
        height: 1fr;
        min-height: 8;
        border: heavy #6EE7B7;
        padding: 1 2;
        margin: 0 2 1 2;
    }
    .output-title {
        text-style: bold;
        color: #6EE7B7;
        margin-bottom: 1;
    }
    #results-view {
        scrollbar-size: 1 1;
        overflow-y: auto;
        height: 1fr;
    }
    """

    def __init__(self, events_folder: str = ".devsper/events", *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._events_folder = events_folder
        self._event_log_path: str | None = None
        self._last_scheduler = None
        self._last_reasoning_store = None
        self._run_thread: threading.Thread | None = None
        self._last_prompt = ""
        self._loading_timer = None
        self._current_swarm = None
        self._paused = False
        self._default_subtitle = "Distributed AI Swarm Runtime"
        self._last_mission_snapshot: dict = {}

    def compose(self) -> ComposeResult:
        yield devsperLayout()
        yield Footer()

    def on_mount(self) -> None:
        try:
            self.set_focus(self.query_one("#prompt-input"))
        except Exception:
            pass

    def _get_results_view(self):
        return self.query_one("#results-view")

    def _run_swarm_worker(self, prompt: str) -> None:
        """Run swarm in background thread."""
        try:
            mission_prompt = (prompt or "").strip()
            mission_prefixes = ("mission:research", "mission:coding", "mission:experiment")
            if mission_prompt.lower().startswith(mission_prefixes):
                self._run_mission_worker(mission_prompt)
                return
            from devsper.config import get_config
            from devsper.utils.event_logger import EventLog
            from devsper.swarm.swarm import Swarm
            from devsper.memory.memory_router import MemoryRouter
            from devsper.memory.memory_store import get_default_store
            from devsper.memory.memory_index import MemoryIndex

            cfg = get_config()
            event_log = EventLog(events_folder_path=self._events_folder)
            self._event_log_path = event_log.log_path
            memory_router = MemoryRouter(
                store=get_default_store(),
                index=MemoryIndex(
                    get_default_store(),
                    ranking_backend=getattr(cfg.memory, "backend", "local"),
                ),
                top_k=5,
            )
            swarm = Swarm(
                worker_count=2,
                worker_model=cfg.worker_model,
                planner_model=cfg.planner_model,
                event_log=event_log,
                memory_router=memory_router,
                use_tools=True,
            )
            self._current_swarm = swarm
            swarm.run(prompt)
            self._current_swarm = None
            self._last_scheduler = swarm._last_scheduler
            self._last_reasoning_store = getattr(swarm, "_last_reasoning_store", None)
            self.call_from_thread(self._on_swarm_finished)
        except Exception as err:
            msg = str(err)
            self.call_from_thread(lambda: self._on_swarm_error(msg))

    def _run_mission_worker(self, prompt: str) -> None:
        from devsper.missions import MissionRunner, MissionType

        raw = (prompt or "").strip()
        prefix, _, goal = raw.partition(" ")
        mission_type_raw = prefix.split(":", 1)[1] if ":" in prefix else "research"
        mission_type = MissionType(mission_type_raw)
        runner = MissionRunner()
        result = runner.run(goal=goal.strip(), mission_type=mission_type)
        self._last_mission_snapshot = {
            "mission_id": result.mission_id,
            "goal": result.goal,
            "dag": result.dag,
            "quality_score": result.quality_score,
            "iterations": result.iterations,
            "iteration_history": result.iteration_history,
        }
        self._last_scheduler = None
        self._last_reasoning_store = None
        self.call_from_thread(lambda: self._on_mission_finished(result.output))

    def _on_mission_finished(self, output: str) -> None:
        self._run_thread = None
        self._stop_loading_timer()
        try:
            rv = self._get_results_view()
            if rv is not None and hasattr(rv, "set_loading"):
                rv.set_loading(False)
            if rv is not None and hasattr(rv, "set_exchange"):
                rv.set_exchange(self._last_prompt, output)
        except Exception:
            pass
        self.notify("Mission complete.", severity="information")

    def _on_swarm_finished(self) -> None:
        self._update_ui_after_run()

    def _on_swarm_error(self, msg: str) -> None:
        self._run_thread = None
        self._stop_loading_timer()
        try:
            rv = self._get_results_view()
            if rv is not None and hasattr(rv, "set_loading"):
                rv.set_loading(False)
        except Exception:
            pass
        self.notify(f"Swarm error: {msg}", severity="error")

    def _update_ui_after_run(self) -> None:
        self._run_thread = None
        self._stop_loading_timer()
        try:
            rv = self._get_results_view()
            if rv is not None and hasattr(rv, "set_loading"):
                rv.set_loading(False)
            if rv is None or not hasattr(rv, "set_exchange"):
                return
            response = ""
            if self._last_scheduler is not None:
                completed = self._last_scheduler.get_completed_tasks()
                if completed:
                    last = completed[-1]
                    response = getattr(last, "result", None) or ""
                    if len(completed) > 1 and not response.strip():
                        response = "\n\n".join(
                            getattr(t, "result", "") or "" for t in completed
                        )
            rv.set_exchange(self._last_prompt, response)
        except Exception:
            pass
        self.notify("Done.", severity="information")

    def _read_step_status(self) -> str:
        """Read event log and return a friendly, sequential step status for the current run."""
        path = getattr(self, "_event_log_path", None)
        if not path or not os.path.isfile(path):
            return "Starting…"
        events = []
        try:
            from devsper.types.event import Event

            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(Event.model_validate_json(line))
                    except Exception:
                        continue
        except Exception:
            return "Running…"
        if not events:
            return "Starting…"

        # task_id → description so the UI can label each step
        task_descriptions: dict[str, str] = {}
        for e in events:
            if getattr(e.type, "value", None) != "task_created":
                continue
            p = e.payload or {}
            tid = p.get("task_id")
            desc = p.get("description")
            if tid and desc:
                task_descriptions[tid] = (desc or "").strip()

        def _truncate(s: str, max_len: int = 48) -> str:
            s = (s or "").strip()
            if len(s) <= max_len:
                return s
            return s[: max_len - 1].rstrip() + "…"

        last = events[-1]
        ev_type = getattr(last.type, "value", str(last.type))
        payload = last.payload or {}
        task_id = (payload.get("task_id") or "").strip()
        desc = task_descriptions.get(task_id) if task_id else None
        total_tasks = sum(1 for e in events if getattr(e.type, "value", None) == "task_created")
        completed = sum(1 for e in events if getattr(e.type, "value", None) == "task_completed")
        current_step = completed + 1 if ev_type in ("agent_started", "task_started") else completed

        if ev_type == "swarm_started":
            return "Starting…"
        if ev_type == "planner_started":
            return "Planning your request…"
        if ev_type == "task_created":
            return f"Planned {total_tasks} step(s)…"
        if ev_type == "planner_finished":
            n = payload.get("subtask_count", total_tasks) or total_tasks
            return f"Ready. Executing step 1 of {n}…"
        if ev_type == "executor_started":
            if total_tasks > 0:
                return f"Executing step 1 of {total_tasks}…"
            return "Executing…"
        if ev_type in ("agent_started", "task_started"):
            if total_tasks > 0 and current_step <= total_tasks:
                step_label = f"Step {current_step} of {total_tasks}: "
            else:
                step_label = ""
            if desc:
                return step_label + _truncate(desc)
            return (step_label or "Working on task…").rstrip(": ") or "Working on task…"
        if ev_type in ("task_completed", "agent_finished"):
            if total_tasks > 0:
                if completed < total_tasks:
                    next_n = completed + 1
                    return f"Finished step {completed} of {total_tasks}. Executing step {next_n}…"
                return f"Finished step {completed} of {total_tasks}. Assembling result…"
            return "Finished. Assembling result…"
        if ev_type == "executor_finished":
            return "Assembling final result…"
        if ev_type == "swarm_finished":
            return "Done. Here’s your result."
        return "Running…"

    def _start_loading_timer(self) -> None:
        """Tick spinner and update step status from event log."""
        self._stop_loading_timer()

        def tick() -> None:
            if not (self._run_thread and self._run_thread.is_alive()):
                self._stop_loading_timer()
                return
            try:
                rv = self._get_results_view()
                if rv is not None:
                    step = self._read_step_status()
                    if hasattr(rv, "set_loading"):
                        rv.set_loading(True, step)
                    if hasattr(rv, "tick_loading"):
                        rv.tick_loading()
            except Exception:
                pass

        self._loading_timer = self.set_interval(0.25, tick)

    def _stop_loading_timer(self) -> None:
        if getattr(self, "_loading_timer", None) is not None:
            try:
                self._loading_timer.stop()
            except Exception:
                pass
            self._loading_timer = None

    def _get_prompt_from_input(self) -> str:
        try:
            inp = self.query_one("#prompt-input", Input)
            val = (inp.value or "").strip()
            if val:
                return val
        except Exception:
            pass
        return "Summarize the concept of swarm intelligence in one paragraph."

    def _start_swarm_run(self, prompt: str) -> None:
        """Start swarm with the given prompt (call only when not already running)."""
        self._last_prompt = (prompt or "").strip()
        try:
            rv = self._get_results_view()
            if rv is not None and hasattr(rv, "set_loading"):
                rv.set_loading(True, "Starting…")
        except Exception:
            pass
        self._run_thread = threading.Thread(
            target=self._run_swarm_worker, args=(prompt,), daemon=True
        )
        self._run_thread.start()
        self._start_loading_timer()

    def action_run_swarm(self) -> None:
        """Run swarm with prompt from input (or default). Enter or r to run."""
        if self._run_thread and self._run_thread.is_alive():
            self.notify("Wait for current run to finish.", severity="warning")
            return
        prompt = self._get_prompt_from_input()
        self._start_swarm_run(prompt)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Run swarm when user presses Enter in the prompt input."""
        if event.input.id != "prompt-input":
            return
        if self._run_thread and self._run_thread.is_alive():
            self.notify("Wait for current run to finish.", severity="warning")
            return
        prompt = (event.input.value or "").strip()
        if not prompt:
            self.notify("Type a task above, then Enter or r to run.", severity="warning")
            return
        self._start_swarm_run(prompt)

    def action_focus_output(self) -> None:
        try:
            self.set_focus(self.query_one("#results-view"))
        except Exception:
            pass

    def action_unfocus_input(self) -> None:
        """Move focus off the input so r / q work. Press Esc when stuck in the input."""
        try:
            focused = self.focused
            if focused is not None and getattr(focused, "id", None) == "prompt-input":
                out = self.query_one("#results-view")
                if out.can_focus:
                    self.set_focus(out)
        except Exception:
            pass

    def action_dashboard(self) -> None:
        """Open dashboard screen (tasks, swarm graph, memory, logs)."""
        self.push_screen(
            DashboardScreen(
                app_ref=self,
                event_log_path=getattr(self, "_event_log_path", None),
            )
        )

    def action_toggle_pause(self) -> None:
        """Toggle pause/resume for the current swarm run."""
        swarm = getattr(self, "_current_swarm", None)
        if swarm is None:
            self.notify("No run in progress.", severity="warning")
            return
        self._paused = not self._paused
        if self._paused:
            swarm.pause()
            self.sub_title = "[yellow]⏸ PAUSED[/]"
            self.notify("Paused: current tasks will finish, no new tasks start.", severity="information")
        else:
            swarm.resume()
            self.sub_title = self._default_subtitle
            self.notify("Resumed.", severity="information")

    def action_inject_note(self) -> None:
        """Open overlay to inject a note to the swarm (stored as high-priority memory)."""
        from devsper.tui.inject_screen import InjectScreen
        self.push_screen(InjectScreen())

    def action_quit(self) -> None:
        self.exit()


def run_tui(events_folder: str = ".devsper/events") -> None:
    """Entry point to run the TUI."""
    app = devsperTUI(events_folder=events_folder)
    app.run()
