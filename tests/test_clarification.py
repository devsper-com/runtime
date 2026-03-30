"""
Tests for human-in-the-loop clarification protocol: detector, widget, agent enrichment.
"""

from unittest.mock import patch, MagicMock

from devsper.agents.agent import ClarificationDetector
from devsper.events import (
    ClarificationField,
    ClarificationRequest,
    ClarificationResponse,
)
from devsper.types.task import Task, TaskStatus


# --- ClarificationDetector ---

NUMBERED_QUESTIONS_TEXT = """
To proceed with this analysis, I need a few details from you. Please provide the following:

1) Please provide the corpus or dataset you want me to analyze.

2) What is the desired number of topics? (or say "auto" for automatic selection)

3) Should I include confidence scores for each topic?

4) Output format?

- A: List of topics with keywords
- B: Short theme summaries
- C: Topic clusters
- D: Timeline of themes

5) Any specific sections to include in the report?

6) Preferred language for the output?

7) Should I save intermediate results?
"""


class TestClarificationDetector_DetectsNumberedQuestions:
    def test_returns_clarification_request_with_multiple_fields(self):
        detector = ClarificationDetector()
        result = detector.detect(NUMBERED_QUESTIONS_TEXT)
        assert result is not None
        assert isinstance(result, ClarificationRequest)
        assert len(result.fields) >= 5  # at least 5 numbered + MCQ

    def test_field_4_is_mcq_with_four_options(self):
        detector = ClarificationDetector()
        result = detector.detect(NUMBERED_QUESTIONS_TEXT)
        assert result is not None
        mcq_fields = [f for f in result.fields if (f.get("type") if isinstance(f, dict) else getattr(f, "type", None)) == "mcq"]
        assert len(mcq_fields) >= 1
        mcq = mcq_fields[0]
        opts = mcq.get("options") if isinstance(mcq, dict) else getattr(mcq, "options", None)
        assert opts is not None
        assert len(opts) == 4


class TestClarificationDetector_PassesNormalResponse:
    def test_returns_none_for_progress_response(self):
        detector = ClarificationDetector()
        text = "I found 5 papers matching your query. Here are the results..."
        result = detector.detect(text)
        assert result is None


class TestClarificationDetector_DetectsYesNoQuestion:
    def test_returns_clarification_request_with_confirm_type(self):
        detector = ClarificationDetector()
        text = "Before I proceed, should I include the appendix? (yes/no)"
        result = detector.detect(text)
        assert result is not None
        assert len(result.fields) >= 1
        f = result.fields[0]
        ftype = f.get("type") if isinstance(f, dict) else getattr(f, "type", None)
        assert ftype == "confirm"


# --- ClarificationWidget (mocked Prompt) ---


class TestClarificationWidget_MCQ_RendersOptions:
    def test_returns_option_text_not_letter(self):
        from devsper.cli.ui.run_view import ClarificationWidget
        from devsper.cli.ui.theme import ThemeStyle

        req = ClarificationRequest(
            request_id="req-1",
            task_id="t1",
            agent_role="researcher",
            fields=[
                ClarificationField(
                    type="mcq",
                    question="Output format?",
                    options=["Markdown", "JSON", "Plain text", "CSV"],
                    default=None,
                    required=True,
                ),
            ],
            context="Need format",
        )
        widget = ClarificationWidget(req, ThemeStyle())
        with patch("devsper.cli.ui.run_view.is_interactive", return_value=True):
            with patch("rich.prompt.Prompt.ask", return_value="B"):
                response = widget.render()
        assert response.answers.get("Output format?") == "JSON"


class TestClarificationWidget_MultiSelect_ParsesCSV:
    def test_parses_comma_separated_indices(self):
        from devsper.cli.ui.run_view import ClarificationWidget
        from devsper.cli.ui.theme import ThemeStyle

        req = ClarificationRequest(
            request_id="req-2",
            task_id="t2",
            agent_role="researcher",
            fields=[
                ClarificationField(
                    type="multi_select",
                    question="Select formats",
                    options=["A", "B", "C"],
                    default=None,
                    required=True,
                ),
            ],
            context="Select",
        )
        widget = ClarificationWidget(req, ThemeStyle())
        with patch("devsper.cli.ui.run_view.is_interactive", return_value=True):
            with patch("rich.prompt.Prompt.ask", return_value="1,3"):
                response = widget.render()
        ans = response.answers.get("Select formats")
        assert isinstance(ans, list)
        assert "A" in ans
        assert "C" in ans


class TestClarificationWidget_Timeout_ReturnsSkipped:
    def test_skipped_response_when_timeout(self):
        """When requester returns skipped=True, agent proceeds without blocking."""
        from devsper.agents.agent import Agent
        from devsper.agents.agent import AgentRequest

        task = Task(id="t1", description="Test", dependencies=[], status=TaskStatus.PENDING)
        requester = MagicMock()
        requester.request_clarification = MagicMock(
            return_value=ClarificationResponse(request_id="r1", answers={}, skipped=True)
        )
        agent = Agent(model_name="mock", use_tools=False)
        agent.clarification_requester = requester
        # First generate returns clarifying text, second returns final result
        with patch("devsper.agents.agent.generate", side_effect=[
            "To proceed, please provide the following.\n\n1) Corpus?\n\n2) Format?",
            "Final result.",
        ]):
            req = AgentRequest(
                task=task,
                memory_context="",
                tools=[],
                model="mock",
                system_prompt="You are a test.",
                prefetch_used=False,
            )
            resp = agent.run(req)
        assert requester.request_clarification.called
        assert resp.success is True
        assert "Final result" in (resp.result or "")


class TestClarificationWidget_NonTTY_UsesDefaults:
    def test_no_prompt_asked_when_ci(self):
        from devsper.cli.ui.run_view import ClarificationWidget
        from devsper.cli.ui.theme import ThemeStyle

        req = ClarificationRequest(
            request_id="req-3",
            task_id="t3",
            agent_role="agent",
            fields=[
                ClarificationField(type="mcq", question="X?", options=["A", "B"], default=None, required=True),
            ],
            context="Context",
        )
        widget = ClarificationWidget(req, ThemeStyle())
        with patch("devsper.cli.ui.run_view.is_interactive", return_value=False):
            response = widget.render()
        assert response.skipped is True
        assert response.answers.get("X?") == "A"


class TestAgentClarify_EnrichesTaskContext:
    def test_enrich_task_appends_answers_to_description(self):
        from devsper.agents.agent import Agent

        task = Task(id="t1", description="Do something", dependencies=[], status=TaskStatus.PENDING)
        agent = Agent(model_name="mock", use_tools=False)
        enriched = agent._enrich_task(task, {"format": "Markdown"})
        assert "format: Markdown" in enriched.description
        assert "[User provided clarification:]" in enriched.description


class TestAgentClarify_ResumeAfterResponse:
    def test_agent_completes_after_receive_clarification(self):
        import queue
        from devsper.swarm.executor import Executor
        from devsper.swarm.scheduler import Scheduler
        from devsper.types.task import Task, TaskStatus

        scheduler = Scheduler()
        task = Task(id="t1", description="Ask and complete", dependencies=[], status=TaskStatus.PENDING)
        scheduler.add_tasks([task])
        agent = MagicMock()
        agent.run_task = MagicMock(side_effect=[None, "final result"])
        clarification_bus = queue.Queue()
        executor = Executor(
            scheduler=scheduler,
            agent=agent,
            worker_count=1,
            clarification_bus=clarification_bus,
        )
        response = ClarificationResponse(
            request_id="r1",
            answers={"q": "a"},
            skipped=False,
        )
        executor._pending_clarification_queues["r1"] = (queue.Queue(), "t1")
        executor._pending_clarification_queues["r1"][0].put(response)
        executor.receive_clarification(response)
        assert scheduler.get_task("t1").status == TaskStatus.RUNNING


class TestClarificationDetector_HITLDirective:
    def test_parses_hitl_request_directive_to_mcq(self):
        detector = ClarificationDetector()
        text = (
            "Some preface text that should be ignored.\n"
            "HITL_REQUEST: {"
            '"context":"Choose one option to proceed.",'
            '"priority":1,'
            '"timeout_seconds":120,'
            '"fields":[{'
            '"type":"mcq",'
            '"question":"Pick a path:",'
            '"options":["A) Upload / point to a dataset you already have","B) Collect public data"],'
            '"default":null,'
            '"required":true'
            "}]}"
        )

        result = detector.detect(text)
        assert result is not None
        assert isinstance(result, ClarificationRequest)
        assert len(result.fields) == 1
        f0 = result.fields[0]
        f0_type = f0.get("type") if isinstance(f0, dict) else getattr(f0, "type", None)
        assert f0_type == "mcq"

    def test_malformed_hitl_directive_falls_back_to_none(self):
        detector = ClarificationDetector()
        # This contains the token but invalid JSON. Regex fallback should not
        # trigger because there is no question/options content.
        text = "HITL_REQUEST: {not valid json}"
        result = detector.detect(text)
        assert result is None


class TestAgentHITLToolProtocol:
    def test_build_request_adds_hitl_tool_when_requester_present(self):
        from devsper.agents.agent import Agent

        task = Task(id="t-hitl-1", description="Need clarification", dependencies=[], status=TaskStatus.PENDING)
        agent = Agent(model_name="mock", use_tools=True)
        agent.clarification_requester = MagicMock()
        req = agent.build_request(task)
        assert "hitl.request" in req.tools

    def test_hitl_request_tool_call_routes_to_requester(self):
        from devsper.agents.agent import Agent, AgentRequest

        task = Task(id="t-hitl-2", description="Need dataset choice", dependencies=[], status=TaskStatus.PENDING)
        requester = MagicMock()
        requester.request_clarification = MagicMock(
            return_value=ClarificationResponse(
                request_id="req-fixed",
                answers={"Choose path": "Option B"},
                skipped=False,
            )
        )
        agent = Agent(model_name="mock", use_tools=True)
        agent.clarification_requester = requester

        first = (
            "TOOL: hitl.request\n"
            'INPUT: {"context":"Need path","priority":1,"timeout_seconds":120,'
            '"fields":[{"type":"mcq","question":"Choose path","options":["Option A","Option B"],"required":true}]}\n'
        )
        second = "Final analysis result."
        with patch("devsper.agents.agent.generate", side_effect=[first, second]):
            req = AgentRequest(
                task=task,
                memory_context="",
                tools=["hitl.request"],
                model="mock",
                system_prompt="You are a test.",
                prefetch_used=False,
            )
            resp = agent.run(req)

        assert requester.request_clarification.called
        called_req = requester.request_clarification.call_args[0][0]
        assert called_req.task_id == task.id
        assert len(called_req.fields) == 1
        assert resp.success is True
        assert "Final analysis result." in (resp.result or "")
