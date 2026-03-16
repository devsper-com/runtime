"""
LLM-powered plain-English analysis of a RunReport.
"""

from typing import Callable

from devsper.types.task import TaskStatus
from devsper.intelligence.analysis.run_report import RunReport


def analyze(
    report: RunReport,
    worker_model: str,
    stream_callback: Callable[[str], None] | None = None,
) -> str:
    """
    Call the LLM with a structured prompt; stream the response for progressive CLI display
    when stream_callback is provided. On error return "Analysis unavailable."
    """
    try:
        from devsper.utils.models import generate
    except ImportError:
        return "Analysis unavailable."

    bottleneck_desc = ""
    if report.bottleneck_task_id:
        for t in report.tasks:
            if t.task_id == report.bottleneck_task_id:
                bottleneck_desc = f"{t.description[:80]} ({t.duration_seconds:.1f}s)"
                break
        if not bottleneck_desc:
            bottleneck_desc = report.bottleneck_task_id

    failed_block = []
    for t in report.tasks:
        if t.status == TaskStatus.FAILED:
            failed_block.append(
                f"- {t.description[:100]}: error={t.error or 'unknown'}; tools_that_failed={t.tool_failures or 'none'}"
            )
    failed_text = "\n".join(failed_block) if failed_block else "(none)"

    user_content = f"""Run ID: {report.run_id}
Root task: {report.root_task[:200]}
Duration: {report.total_duration_seconds:.1f}s
Tasks: {report.completed_tasks}/{report.total_tasks} completed, {report.failed_tasks} failed
Bottleneck: {bottleneck_desc}
Failed tasks:
{failed_text}
Tool success rate: {report.tool_success_rate:.1f}%
Peak parallelism: {report.peak_parallelism}"""

    system_content = """You are analyzing a devsper swarm run. Be concise, specific, and actionable.
Focus on: what failed and why, what was slow, what could be improved.
Do not summarize what succeeded unless it's relevant to failures.
Max 200 words."""

    prompt = f"{system_content}\n\n---\n\n{user_content}"

    try:
        out = generate(worker_model, prompt, stream=bool(stream_callback))
        if isinstance(out, str):
            return out.strip() or "Analysis unavailable."
        chunks = []
        for chunk in out:
            if chunk:
                chunks.append(chunk)
                if stream_callback:
                    stream_callback(chunk)
        return "".join(chunks).strip() or "Analysis unavailable."
    except Exception:
        return "Analysis unavailable."
