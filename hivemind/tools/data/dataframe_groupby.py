"""Group CSV by column and show count per group. Requires pandas."""

from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class DataframeGroupbyTool(Tool):
    """Group CSV by a column and return count per group. Requires pandas."""

    name = "dataframe_groupby"
    description = "Group CSV by column and show counts. Requires pandas."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to CSV"},
            "column": {"type": "string", "description": "Column to group by"},
        },
        "required": ["path", "column"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        column = kwargs.get("column")
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not column or not isinstance(column, str):
            return "Error: column must be a non-empty string"
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
            grouped = df.groupby(column).size()
            return grouped.to_string()
        except Exception as e:
            return f"Error: {e}"


register(DataframeGroupbyTool())
