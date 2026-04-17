"""Optional scoring via TruLens + OpenEvals. Requires devsper[eval]."""
from __future__ import annotations

import json

AVAILABLE_METRICS = ["relevance", "groundedness", "coherence", "correctness"]


def score_results(results: list[dict], metrics: list[str]) -> list[dict]:
    """Score eval results using OpenEvals LLM-as-judge.

    Returns results with a ``scores`` key added to each entry.
    Requires ``pip install 'devsper[eval]'``.
    """
    try:
        from openevals.llm import create_llm_grader  # noqa: PLC0415
    except ImportError:
        raise ImportError(
            "Scoring requires: pip install 'devsper[eval]'"
        )

    scored: list[dict] = []
    for result in results:
        scores: dict[str, float] = {}
        if not result.get("success"):
            result["scores"] = scores
            scored.append(result)
            continue

        query = result.get("inputs", {}).get("query", "")
        output = result.get("output", "")
        expected = result.get("expected", "")

        for metric in metrics:
            try:
                if metric == "relevance":
                    grader = create_llm_grader(
                        model="openai/gpt-4o-mini",
                        prompt=(
                            "Score 0-1 how relevant the response is to the input query. "
                            "Return only a JSON object with key 'score'."
                        ),
                    )
                    scores["relevance"] = grader(inputs=query, outputs=output)
                elif metric == "correctness" and expected:
                    grader = create_llm_grader(
                        model="openai/gpt-4o-mini",
                        prompt=(
                            "Score 0-1 how correct the response is compared to the expected answer. "
                            "Return only a JSON object with key 'score'."
                        ),
                    )
                    scores["correctness"] = grader(
                        inputs=query, outputs=output, reference_outputs=expected
                    )
                # groundedness and coherence: skipped until openevals exposes them
            except Exception as e:  # noqa: BLE001
                # Don't let one metric failure abort the whole result
                import warnings  # noqa: PLC0415
                warnings.warn(f"Metric '{metric}' scoring failed: {e}", stacklevel=2)

        result["scores"] = scores
        scored.append(result)

    return scored


def record_to_trulens(results: list[dict], app_name: str = "devsper") -> None:
    """Ship eval results to TruLens for dashboard viewing.

    Silently skips if TruLens is not installed or the API has changed.
    """
    try:
        from trulens.core import TruSession  # noqa: PLC0415
    except ImportError:
        return

    try:
        session = TruSession()
        for r in results:
            if r.get("success"):
                try:
                    session.add_record(
                        app_id=app_name,
                        input=json.dumps(r.get("inputs", {})),
                        output=r.get("output", ""),
                        latency=r.get("latency_ms", 0) / 1000.0,
                        cost=None,
                        ts=None,
                    )
                except Exception as e:  # noqa: BLE001
                    import warnings  # noqa: PLC0415
                    warnings.warn(f"TruLens record failed: {e}", stacklevel=2)
    except Exception as e:  # noqa: BLE001
        import warnings  # noqa: PLC0415
        warnings.warn(f"TruLens session init failed: {e}", stacklevel=2)
