"""Filter a CSV by column value (simple equality). Requires pandas."""

from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class DataframeFilterTool(Tool):
    """Filter CSV rows where column equals value. Requires pandas."""

    name = "dataframe_filter"
    description = "Filter CSV by column value. Returns matching rows as string. Requires pandas."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to CSV"},
            "column": {"type": "string", "description": "Column name"},
            "value": {"type": "string", "description": "Value to match (string)"},
        },
        "required": ["path", "column", "value"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        column = kwargs.get("column")
        value = kwargs.get("value")
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not column or not isinstance(column, str):
            return "Error: column must be a non-empty string"
        if value is None:
            return "Error: value is required"
        try:
            import pandas as pd
        except ImportError:
            return "Error: pandas required. Install with: pip install pandas"
        p = Path(path)
        if not p.exists() or not p.is_file():
            return f"Error: file not found: {path}"
        try:
            df = pd.read_csv(p)
            if column not in df.columns:
                return f"Error: column '{column}' not in {list(df.columns)}"
            filtered = df[df[column].astype(str) == str(value)]
            return filtered.to_string() if not filtered.empty else "No matching rows."
        except Exception as e:
            return f"Error: {e}"


register(DataframeFilterTool())
