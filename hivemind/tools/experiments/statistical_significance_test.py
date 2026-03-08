"""Simple statistical significance: compare two samples with a t-statistic (no scipy)."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register

try:
    import numpy as np
except ImportError:
    np = None


class StatisticalSignificanceTestTool(Tool):
    """
    Compute pooled t-statistic for two samples (no p-value; report t and approximate interpretation).
    """

    name = "statistical_significance_test"
    description = "Compare two samples with t-statistic (pooled)."
    input_schema = {
        "type": "object",
        "properties": {
            "sample_a": {"type": "array", "items": {"type": "number"}, "description": "First sample"},
            "sample_b": {"type": "array", "items": {"type": "number"}, "description": "Second sample"},
        },
        "required": ["sample_a", "sample_b"],
    }

    def run(self, **kwargs) -> str:
        sample_a = kwargs.get("sample_a")
        sample_b = kwargs.get("sample_b")
        if not sample_a or not isinstance(sample_a, list):
            return "Error: sample_a must be a non-empty list of numbers"
        if not sample_b or not isinstance(sample_b, list):
            return "Error: sample_b must be a non-empty list of numbers"
        if np is None:
            return "Error: numpy is required for this tool"
        try:
            a = np.array(sample_a, dtype=float)
            b = np.array(sample_b, dtype=float)
            a, b = a[~np.isnan(a)], b[~np.isnan(b)]
        except (ValueError, TypeError):
            return "Error: values must be numeric"
        if len(a) < 2 or len(b) < 2:
            return "Error: need at least 2 values per sample"
        n1, n2 = len(a), len(b)
        m1, m2 = np.mean(a), np.mean(b)
        s1, s2 = np.std(a, ddof=1), np.std(b, ddof=1)
        if s1 == 0 and s2 == 0:
            return "No variance in one or both samples; t-test not defined."
        pooled = ((n1 - 1) * s1**2 + (n2 - 1) * s2**2) / (n1 + n2 - 2)
        pooled = max(pooled ** 0.5, 1e-10)
        t = (m1 - m2) / (pooled * (1 / n1 + 1 / n2) ** 0.5)
        return f"Pooled t-statistic: {t:.4f}. Mean A: {m1:.4f}, Mean B: {m2:.4f}. |t|>2 often suggests difference at ~5% level."


register(StatisticalSignificanceTestTool())
