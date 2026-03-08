"""
Response panel: LLM-style. Shows "You asked" + cleaned response (real content only).
"""

import re
from textual.widgets import Static


def _collapse_long_tool_results(text: str, max_keep: int = 120) -> str:
    """Replace long 'Tool result (name): ...' blocks with [output omitted] so we don't dump code/file contents."""
    if not text or "Tool result (" not in text:
        return text
    pattern = re.compile(
        r"(Tool result\s*\(\s*\w+\s*\)\s*:\s*\n?)(.*?)(?=Tool result\s*\(\s*\w+\s*\)\s*:|Response:\n|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    def repl(m):
        prefix, content = m.group(1), (m.group(2) or "").strip()
        if len(content) <= max_keep and content.count("\n") <= 1:
            return m.group(0)
        return prefix + "[output omitted]\n"
    return pattern.sub(repl, text)


def _extract_real_content(text: str) -> str:
    """Keep only the actual answer: remove all agent boilerplate."""
    if not text or not text.strip():
        return ""
    out = text.strip()
    out = _collapse_long_tool_results(out)
    out = re.sub(
        r"Completed:\s*You are an AI worker in a distributed system\.?\s*",
        "",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(r"Task:\s*\n\s*[^\n]*", "", out, flags=re.IGNORECASE)
    out = re.sub(r"^Task:\s*$", "", out, flags=re.MULTILINE | re.IGNORECASE)
    out = re.sub(
        r"RELEVANT MEMORY\s*\([^)]*\)\s*:?\s*\n(?:\s*-\s*[^\n]*\n?)*",
        "",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"RELEVANT MEMORY\s*\n(?:\s*-\s*[^\n]*\n?)*",
        "",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(r"^RELEVANT MEMORY\s*$", "", out, flags=re.MULTILINE | re.IGNORECASE)
    out = re.sub(r"\(previous research notes[^)]*\)", "", out, flags=re.IGNORECASE)
    out = re.sub(
        r"^(?:First|Second|Third|Fourth|Fifth|Sixth)\s+step\s*$",
        "",
        out,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    out = re.sub(r"^\.\.\.\s*$", "", out, flags=re.MULTILINE)
    out = re.sub(r"^—\s*$", "", out, flags=re.MULTILINE)
    out = re.sub(r"^\s*-\s*[a-f0-9]{8}[^\n]*$", "", out, flags=re.MULTILINE)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

class ResultsView(Static):
    """LLM-style: shows last question + cleaned response (real content only)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._prompt = ""
        self._response = ""
        self._loading = False
        self._loading_message = "Running…"
        self._spinner_index = 0

    def set_loading(self, running: bool, message: str = "Running…") -> None:
        self._loading = running
        self._loading_message = message or "Running…"
        self._refresh_display()

    def tick_loading(self) -> None:
        if not self._loading:
            return
        self._spinner_index = (self._spinner_index + 1) % len(SPINNER)
        self._refresh_display()

    def set_exchange(self, prompt: str, response: str) -> None:
        """Set the last user prompt and the cleaned response (LLM-style)."""
        self._prompt = (prompt or "").strip()
        raw = (response or "").strip()
        cleaned = _extract_real_content(raw)
        self._response = cleaned if cleaned else ""
        self._refresh_display()

    def set_output(self, text: str, strip_boilerplate: bool = True) -> None:
        """Legacy: set response only (no prompt)."""
        raw = (text or "").strip()
        cleaned = _extract_real_content(raw) if strip_boilerplate else raw
        self._response = cleaned if cleaned else raw
        self._refresh_display()

    def clear_output(self) -> None:
        self._prompt = ""
        self._response = ""
        self._refresh_display()

    def _refresh_display(self) -> None:
        if self._loading:
            parts = []
            if self._prompt:
                parts.append(f"You asked: {self._prompt}\n")
            parts.append(f"{SPINNER[self._spinner_index]} {self._loading_message}")
            self.update("\n".join(parts))
            return
        if not self._response and not self._prompt:
            self.update(
                "Ask something above and press Enter or r to run.\n\n"
                "Your response will appear here."
            )
            return
        parts = []
        if self._prompt:
            parts.append(f"You asked: {self._prompt}\n")
        parts.append(
            self._response
            if self._response
            else "No substantive output yet. Set OPENAI_API_KEY (or another provider) and run again for the full response."
        )
        self.update("\n".join(parts))

    @property
    def can_focus(self) -> bool:
        return True

    def on_mount(self) -> None:
        self._refresh_display()
