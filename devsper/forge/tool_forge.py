"""
Dynamic Tool Forge — synthesize, validate, and register new tools at runtime.

Agents call ToolForge.synthesize() when no existing tool handles a subtask.
The LLM generates a valid Tool subclass, which is validated for syntax and safety,
executed in a restricted namespace, then registered in the global tool registry.
"""

import ast
import json
import logging
import math
import os
import re
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from devsper.tools.base import Tool
from devsper.tools.registry import register, get

log = logging.getLogger(__name__)

FORGE_SYSTEM_PROMPT = """You are a tool synthesis engine for an AI agent framework.
Generate a Python class that extends devsper's Tool base class.

Rules:
- Class must extend Tool (already imported as `from devsper.tools.base import Tool`)
- Must have: name (str), description (str), input_schema (dict with JSON Schema), run(**kwargs) -> str
- run() must return a string (JSON stringify dicts/lists)
- NO external imports except: json, re, os, pathlib, subprocess, ast, textwrap, typing, dataclasses, math, datetime, itertools, collections
- NO network calls, NO file writes outside /tmp
- Keep it focused and minimal

Return ONLY the Python class code, no preamble, no markdown fences."""

FORGE_USER_TEMPLATE = """Create a tool that: {description}

Example input the tool will receive: {example_input}

Write the complete Tool subclass now."""

# Patterns that indicate unsafe code
_SAFETY_DENY = [
    "import requests",
    "import httpx",
    "import urllib",
    "import http.client",
    "__import__",
    "exec(",
    "eval(",
]


@dataclass
class ForgeResult:
    """Result of a tool synthesis attempt."""

    success: bool
    tool_name: str = ""
    tool: Optional[Tool] = None
    error: str = ""
    code: str = ""


class ToolForge:
    """
    Synthesize new Tool subclasses at runtime using an LLM.

    Usage::

        forge = ToolForge()
        result = forge.synthesize(
            description="Convert celsius to fahrenheit",
            example_input={"celsius": 100},
        )
        if result.success:
            # result.tool is now registered and ready to use
            print(result.tool_name)
    """

    def synthesize(
        self,
        description: str,
        example_input: Optional[dict] = None,
    ) -> ForgeResult:
        """
        Generate, validate, and register a new Tool subclass.

        Args:
            description: Natural language description of what the tool should do.
            example_input: Optional dict of example kwargs the tool will receive.

        Returns:
            ForgeResult with success=True and the registered tool instance on success,
            or success=False with an error message on failure.
        """
        if example_input is None:
            example_input = {}

        prompt = FORGE_USER_TEMPLATE.format(
            description=description,
            example_input=json.dumps(example_input),
        )

        log.info("ToolForge: synthesizing tool for: %s", description[:80])

        try:
            raw_code = self._call_llm(prompt, FORGE_SYSTEM_PROMPT)
        except Exception as exc:
            return ForgeResult(success=False, error=f"LLM call failed: {exc}")

        code = self._strip_fences(raw_code)

        # Syntax validation
        try:
            ast.parse(code)
        except SyntaxError as exc:
            return ForgeResult(success=False, error=f"SyntaxError in generated code: {exc}", code=code)

        # Safety check
        safety_error = self._safety_check(code)
        if safety_error:
            return ForgeResult(success=False, error=safety_error, code=code)

        # Execute in restricted namespace
        namespace: dict = {
            "Tool": Tool,
            "json": json,
            "re": re,
            "os": os,
            "Path": Path,
            "ast": ast,
            "textwrap": textwrap,
            "math": math,
            "datetime": datetime,
            "__builtins__": {
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "set": set,
                "len": len,
                "range": range,
                "enumerate": enumerate,
                "zip": zip,
                "map": map,
                "filter": filter,
                "sorted": sorted,
                "reversed": reversed,
                "sum": sum,
                "min": min,
                "max": max,
                "abs": abs,
                "round": round,
                "isinstance": isinstance,
                "issubclass": issubclass,
                "hasattr": hasattr,
                "getattr": getattr,
                "setattr": setattr,
                "print": print,
                "repr": repr,
                "type": type,
                "ValueError": ValueError,
                "TypeError": TypeError,
                "KeyError": KeyError,
                "IndexError": IndexError,
                "Exception": Exception,
                "RuntimeError": RuntimeError,
                "NotImplementedError": NotImplementedError,
                "StopIteration": StopIteration,
                "True": True,
                "False": False,
                "None": None,
            },
        }

        try:
            exec(code, namespace)  # noqa: S102
        except Exception as exc:
            return ForgeResult(success=False, error=f"Execution error: {exc}", code=code)

        # Find the Tool subclass in namespace
        tool_cls = None
        for obj in namespace.values():
            try:
                if (
                    isinstance(obj, type)
                    and issubclass(obj, Tool)
                    and obj is not Tool
                ):
                    tool_cls = obj
                    break
            except TypeError:
                continue

        if tool_cls is None:
            return ForgeResult(
                success=False,
                error="No Tool subclass found in generated code.",
                code=code,
            )

        try:
            instance = tool_cls()
        except Exception as exc:
            return ForgeResult(success=False, error=f"Failed to instantiate tool: {exc}", code=code)

        if not instance.name:
            return ForgeResult(success=False, error="Tool must have a non-empty name.", code=code)

        # Register — gracefully handle duplicates (overwrite is fine per registry contract)
        try:
            register(instance)
            log.info("ToolForge: registered tool '%s'", instance.name)
        except Exception as exc:
            log.warning("ToolForge: registration warning for '%s': %s", instance.name, exc)

        return ForgeResult(
            success=True,
            tool_name=instance.name,
            tool=instance,
            code=code,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, system: str) -> str:
        """Call the configured LLM router synchronously."""
        from devsper.providers.router.factory import get_llm_router
        from devsper.providers.router.base import LLMRequest
        import asyncio

        router = get_llm_router()
        if router is None:
            raise RuntimeError("No LLM router configured. Set an LLM provider API key.")

        req = LLMRequest(
            model="auto",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2048,
            temperature=0.2,
        )
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(router.route(req))
            return resp.content
        finally:
            loop.close()

    @staticmethod
    def _strip_fences(code: str) -> str:
        """Remove markdown code fences if the LLM wrapped the output."""
        code = code.strip()
        # Remove ```python ... ``` or ``` ... ```
        if code.startswith("```"):
            lines = code.splitlines()
            # Drop the first line (```python or ```)
            lines = lines[1:]
            # Drop the last ``` if present
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines)
        return code.strip()

    @staticmethod
    def _safety_check(code: str) -> str:
        """
        Return an error message string if unsafe patterns are found, else empty string.

        Checks for disallowed imports and dangerous builtins.
        Also rejects open() calls with write modes.
        """
        for pattern in _SAFETY_DENY:
            if pattern in code:
                return f"Safety check failed: '{pattern}' is not allowed in forge-generated tools."

        # Reject open() with write modes
        write_mode_pattern = re.compile(r'\bopen\s*\(.*["\'][wa+]["\']', re.DOTALL)
        if write_mode_pattern.search(code):
            # Allow writes only to /tmp
            # More precise: any open() with write mode that isn't clearly /tmp is rejected
            # For simplicity, reject all write-mode opens outside /tmp paths
            suspicious = re.findall(r'\bopen\s*\([^)]+\)', code)
            for call in suspicious:
                if re.search(r'["\'][wa+]["\']', call):
                    if "/tmp" not in call and "tmp" not in call.lower():
                        return f"Safety check failed: file writes outside /tmp are not allowed."

        return ""
