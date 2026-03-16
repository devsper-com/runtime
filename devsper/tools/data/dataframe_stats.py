"""Compute basic statistics for a CSV as a dataframe (requires pandas)."""

from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class DataframeStatsTool(Tool):
    """Load CSV as dataframe and return describe() stats. Requires pandas."""

    name = "dataframe_stats"
    description = "Compute summary statistics for a CSV file. Requires pandas."
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Path to CSV file"}},
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        try:
            import pandas as pd
        except ImportError:
            return "Error: pandas required. Install with: pip install pandas"
        p = Path(path)
        if not p.exists() or not p.is_file():
            return f"Error: file not found: {path}"
        try:
            df = pd.read_csv(p)
            return str(df.describe())
        except Exception as e:
            return f"Error: {e}"


register(DataframeStatsTool())
