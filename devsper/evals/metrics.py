"""
Built-in eval metrics.

Each metric is a function: (case: EvalCase, actual: str) -> float in [0, 1].
"""

from __future__ import annotations

import re

from devsper.evals.types import EvalCase


def exact_match(case: EvalCase, actual: str) -> float:
    """1.0 if actual.strip() == expected.strip(), else 0.0."""
    return 1.0 if (actual or "").strip() == (case.expected or "").strip() else 0.0


def contains(case: EvalCase, actual: str) -> float:
    """1.0 if expected substring is anywhere in actual (case-insensitive)."""
    return 1.0 if (case.expected or "").lower() in (actual or "").lower() else 0.0


def regex_match(case: EvalCase, actual: str) -> float:
    """1.0 if actual matches the regex pattern stored in expected."""
    try:
        return 1.0 if re.search(case.expected, actual or "", re.IGNORECASE | re.DOTALL) else 0.0
    except re.error:
        return 0.0


def non_empty(case: EvalCase, actual: str) -> float:
    """1.0 if actual is non-empty (useful as a sanity-check baseline)."""
    return 1.0 if (actual or "").strip() else 0.0


def word_overlap(case: EvalCase, actual: str) -> float:
    """F1-style token overlap between expected and actual."""
    expected_tokens = set((case.expected or "").lower().split())
    actual_tokens = set((actual or "").lower().split())
    if not expected_tokens:
        return 1.0
    if not actual_tokens:
        return 0.0
    overlap = expected_tokens & actual_tokens
    precision = len(overlap) / len(actual_tokens)
    recall = len(overlap) / len(expected_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def llm_judge(model: str = "gpt-4o-mini"):
    """
    Return a metric function that uses an LLM to score the output.

    Usage::

        metric = llm_judge(model="gpt-4o-mini")
        score = metric(case, actual)
    """

    def _judge(case: EvalCase, actual: str) -> float:
        from devsper.utils.models import generate

        prompt = (
            "You are an evaluator. Score how well the ACTUAL output satisfies "
            "the TASK and matches the EXPECTED answer. "
            "Respond with ONLY a number between 0.0 and 1.0.\n\n"
            f"TASK: {case.task}\n\n"
            f"EXPECTED: {case.expected}\n\n"
            f"ACTUAL: {(actual or '')[:3000]}\n\n"
            "Score (0.0-1.0):"
        )
        try:
            raw = (generate(model, prompt) or "0").strip()
            # Extract first float-like token
            m = re.search(r"\d+(?:\.\d+)?", raw)
            val = float(m.group(0)) if m else 0.0
            return max(0.0, min(1.0, val))
        except Exception:
            return 0.0

    _judge.__name__ = f"llm_judge[{model}]"
    return _judge


BUILTIN_METRICS: dict[str, object] = {
    "exact_match": exact_match,
    "contains": contains,
    "regex_match": regex_match,
    "non_empty": non_empty,
    "word_overlap": word_overlap,
}


def openevals_metric(evaluator_name: str, model: str = "openai:gpt-4o-mini"):
    """
    Wrap an OpenEvals evaluator as a MetricFn.

    Requires: pip install devsper[openevals]

    ``evaluator_name`` selects a prebuilt evaluator:
      - "correctness"     — LLM judge: does output correctly answer the task?
      - "conciseness"     — LLM judge: is output concise?
      - "groundedness"    — RAG: is output grounded in the reference?
      - "relevance"       — RAG: is output relevant to the question?
      - "code_execution"  — runs Python code in a sandbox (needs e2b)
      - "trajectory"      — agent tool-call sequence matching
      - any custom prompt string starting with a capital letter is treated as
        a raw LLM-as-judge prompt (must contain {inputs}, {outputs},
        {reference_outputs})

    Usage::

        from devsper.evals.metrics import openevals_metric
        metric = openevals_metric("correctness")
        score = metric(case, actual)  # returns float in [0, 1]
    """
    _PREBUILT_PROMPTS = {
        "correctness": (
            "You are an expert evaluator. Given a task and an output, "
            "score the correctness of the output from 0.0 to 1.0.\n\n"
            "Task: {inputs}\nExpected: {reference_outputs}\nActual: {outputs}\n\n"
            "Return a JSON object: {{\"score\": <float 0-1>, \"comment\": \"<reason>\"}}"
        ),
        "conciseness": (
            "You are an expert evaluator. Score the conciseness of the output "
            "(1.0 = perfectly concise, 0.0 = very verbose/redundant).\n\n"
            "Task: {inputs}\nOutput: {outputs}\n\n"
            "Return JSON: {{\"score\": <float 0-1>, \"comment\": \"<reason>\"}}"
        ),
        "groundedness": (
            "You are an expert evaluator. Score whether the output is grounded "
            "in the reference (1.0 = fully grounded, 0.0 = hallucinated).\n\n"
            "Reference: {reference_outputs}\nOutput: {outputs}\n\n"
            "Return JSON: {{\"score\": <float 0-1>, \"comment\": \"<reason>\"}}"
        ),
        "relevance": (
            "You are an expert evaluator. Score how relevant the output is to "
            "the question (1.0 = highly relevant, 0.0 = irrelevant).\n\n"
            "Question: {inputs}\nOutput: {outputs}\n\n"
            "Return JSON: {{\"score\": <float 0-1>, \"comment\": \"<reason>\"}}"
        ),
    }

    def _metric(case: EvalCase, actual: str) -> float:
        try:
            from openevals.llm import create_llm_as_judge
            prompt = _PREBUILT_PROMPTS.get(evaluator_name, evaluator_name)
            evaluator = create_llm_as_judge(prompt=prompt, model=model)
            result = evaluator(
                inputs=case.task,
                outputs=actual or "",
                reference_outputs=case.expected or "",
            )
            raw_score = result.get("score", 0)
            # OpenEvals returns bool or float
            if isinstance(raw_score, bool):
                return 1.0 if raw_score else 0.0
            return max(0.0, min(1.0, float(raw_score)))
        except ImportError:
            # Graceful fallback: use our built-in llm_judge
            return llm_judge(model=model.split(":")[-1])(case, actual)
        except Exception:
            return 0.0

    _metric.__name__ = f"openevals[{evaluator_name}]"
    return _metric


def get_metric(name: str, **kwargs):
    """
    Resolve a metric by name.

    Names:
      - built-in: exact_match, contains, regex_match, non_empty, word_overlap
      - llm_judge           — built-in LLM judge (kwarg: model)
      - openevals:<name>    — OpenEvals evaluator (kwarg: model)
        e.g. "openevals:correctness", "openevals:groundedness"
    """
    if name == "llm_judge":
        return llm_judge(model=kwargs.get("model", "gpt-4o-mini"))
    if name.startswith("openevals:"):
        evaluator_name = name.split(":", 1)[1]
        return openevals_metric(evaluator_name, model=kwargs.get("model", "openai:gpt-4o-mini"))
    if name not in BUILTIN_METRICS:
        raise ValueError(
            f"Unknown metric '{name}'. Available: {list(BUILTIN_METRICS)}, "
            f"llm_judge, openevals:<name>"
        )
    return BUILTIN_METRICS[name]
