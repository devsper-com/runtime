"""Detect potential bias: check balance of a categorical variable (e.g. class or group)."""

from collections import Counter

from devsper.tools.base import Tool
from devsper.tools.registry import register


class DatasetBiasDetectorTool(Tool):
    """
    Detect potential class/group imbalance: report distribution of a categorical variable.
    """

    name = "dataset_bias_detector"
    description = "Detect potential bias: report balance of a categorical (e.g. class) distribution."
    input_schema = {
        "type": "object",
        "properties": {
            "values": {
                "type": "array",
                "items": {},
                "description": "List of categorical values (e.g. labels or group IDs)",
            },
            "imbalance_ratio_threshold": {"type": "number", "description": "Flag if max/min count ratio > this (default 10)"},
        },
        "required": ["values"],
    }

    def run(self, **kwargs) -> str:
        values = kwargs.get("values")
        threshold = kwargs.get("imbalance_ratio_threshold", 10.0)
        if not values or not isinstance(values, list):
            return "Error: values must be a non-empty list"
        counts = Counter(str(v) for v in values)
        if len(counts) < 2:
            return "Need at least 2 distinct categories to assess balance."
        total = sum(counts.values())
        max_c, min_c = max(counts.values()), min(counts.values())
        ratio = max_c / min_c if min_c > 0 else float("inf")
        lines = ["Bias / balance report", "=" * 40, f"Total: {total}, Categories: {len(counts)}", f"Max/min count ratio: {ratio:.1f}"]
        if ratio > threshold:
            lines.append("Imbalance detected (ratio > threshold).")
        for label, c in counts.most_common(15):
            pct = 100 * c / total
            lines.append(f"  {label}: {c} ({pct:.1f}%)")
        return "\n".join(lines)


register(DatasetBiasDetectorTool())
