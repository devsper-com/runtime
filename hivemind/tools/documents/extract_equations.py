"""Extract equation-like content (LaTeX, code blocks) from docproc markdown."""

import re
from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.tools.documents._docproc import run_docproc_to_markdown


class ExtractEquationsTool(Tool):
    """Extract equations from document: LaTeX ($...$) and math code blocks."""

    name = "extract_equations"
    description = "Extract equations (LaTeX and math blocks) from document via docproc."
    input_schema = {
        "type": "object",
        "properties": {"file_path": {"type": "string", "description": "Path to the document"}},
        "required": ["file_path"],
    }

    def run(self, **kwargs) -> str:
        file_path = kwargs.get("file_path")
        if not file_path or not isinstance(file_path, str):
            return "Error: file_path must be a non-empty string"
        content, err = run_docproc_to_markdown(file_path)
        if err:
            return err
        inline = re.findall(r"\$([^$]+)\$", content)
        block = re.findall(r"\$\$([^$]+)\$\$", content)
        code_blocks = re.findall(r"```(?:\w*)\n(.*?)```", content, re.DOTALL)
        equations = block + inline + [c.strip() for c in code_blocks if "\\" in c or "=" in c][:10]
        if not equations:
            return "No equations found in extracted markdown."
        return "Equations:\n" + "\n---\n".join(equations[:30])


register(ExtractEquationsTool())
