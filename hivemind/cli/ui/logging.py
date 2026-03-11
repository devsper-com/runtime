"""
Structured logger matching tracing (Rust) compact format for visual consistency.
All subsystems use get_logger(target) instead of logging.getLogger().
"""

import os
import sys
from datetime import datetime, timezone
from typing import Any

# Log level: 0=TRACE, 1=DEBUG, 2=INFO, 3=WARN, 4=ERROR. Controlled by env/global.
_CLI_LOG_LEVEL = 2  # INFO default


def set_log_level(level: str | int) -> None:
    """level: 'trace'|'debug'|'info'|'warn'|'error' or 0-4."""
    global _CLI_LOG_LEVEL
    if isinstance(level, int):
        _CLI_LOG_LEVEL = level
        return
    _CLI_LOG_LEVEL = {"trace": 0, "debug": 1, "info": 2, "warn": 3, "warning": 3, "error": 4}.get((level or "").lower(), 2)


def get_log_level() -> int:
    return _CLI_LOG_LEVEL


# Target -> style for the target column
TARGET_STYLES = {
    "planner": "hive.planner",
    "executor": "hive.secondary",
    "agent": "hive.agent",
    "tool": "hive.tool",
    "memory": "hive.agent",
    "scheduler": "hive.muted",
    "bus": "hive.dim",
    "swarm": "hive.primary",
    "hitl": "hive.warning",
}


def _level_style(level: str) -> str:
    if level == "WARN":
        return "hive.warning"
    if level == "ERROR":
        return "hive.error"
    if level == "DEBUG":
        return "hive.muted"
    if level == "TRACE":
        return "hive.dim"
    return ""


def _format_ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S.") + f"{datetime.now().microsecond // 1000:03d}"


class HivemindLogger:
    """Logger that emits tracing-compatible compact lines: timestamp  LEVEL  target  message  key=val ..."""

    def __init__(self, target: str, run_id_short: str = "") -> None:
        self.target = target
        self.run_id_short = (run_id_short or "")[:8]

    def _emit(self, level: str, message: str, **fields: Any) -> None:
        lvl_num = {"TRACE": 0, "DEBUG": 1, "INFO": 2, "WARN": 3, "ERROR": 4}.get(level, 2)
        if lvl_num < _CLI_LOG_LEVEL:
            return
        ts = _format_ts()
        target_style = TARGET_STYLES.get(self.target, "hive.muted")
        level_style = _level_style(level)
        parts: list[str] = [ts, "  ", level, "  ", self.target, "  ", message]
        if fields:
            pairs = "  ".join(f"{k}={v}" for k, v in fields.items())
            parts.append("  ")
            parts.append(pairs)
        if self.run_id_short:
            parts.append("  ")
            parts.append(f"run_id={self.run_id_short}")
        line = "".join(parts)
        # Use Rich markup for colors when printing
        try:
            from hivemind.cli.ui.theme import err_console
            if level_style:
                line = f"[{level_style}]{level}[/]  [{target_style}]{self.target}[/]  {message}"
                if fields:
                    line += "  " + "  ".join(f"[hive.muted]{k}={v}[/]" for k, v in fields.items())
                if self.run_id_short:
                    line += f"  [hive.muted]run_id={self.run_id_short}[/]"
                line = f"[hive.muted]{ts}[/]  " + line
            else:
                line = f"[hive.muted]{ts}[/]  {level}  [{target_style}]{self.target}[/]  {message}"
                if fields:
                    line += "  " + "  ".join(f"[hive.muted]{k}={v}[/]" for k, v in fields.items())
                if self.run_id_short:
                    line += f"  [hive.muted]run_id={self.run_id_short}[/]"
            err_console.print(line)
        except Exception:
            print(line, file=sys.stderr)

    def trace(self, message: str, **fields: Any) -> None:
        self._emit("TRACE", message, **fields)

    def debug(self, message: str, **fields: Any) -> None:
        self._emit("DEBUG", message, **fields)

    def info(self, message: str, **fields: Any) -> None:
        self._emit("INFO", message, **fields)

    def warning(self, message: str, **fields: Any) -> None:
        self._emit("WARN", message, **fields)

    def error(self, message: str, **fields: Any) -> None:
        self._emit("ERROR", message, **fields)


def get_logger(target: str, run_id: str = "") -> HivemindLogger:
    """Return logger bound to target name. run_id shortened to 8 chars in output."""
    short = (run_id or "")[:8]
    return HivemindLogger(target, short)
