"""Evaluate if: expressions safely (no eval)."""

import re
from typing import Any

from hivemind.workflow.context import WorkflowContext


class WorkflowConditionError(Exception):
    """Raised when a condition expression cannot be parsed or is invalid."""

    pass


# Pattern: steps.<id>.<field> <op> <value>
# id/field: word chars and underscore
# op: ==, !=, >=, <=, >, <, in, not in
# value: quoted string, int, float, true/false
_EXPR_PATTERN = re.compile(
    r"^\s*steps\.([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*"
    r"(==|!=|>=|<=|>|<|in|not\s+in)\s*(.+)\s*$",
    re.IGNORECASE,
)


def _parse_value(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        raise WorkflowConditionError("Empty value in condition")
    # List: [ ... ]
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_parse_value(p.strip()) for p in _split_top_level(inner, ",")]
    # Quoted string
    if (raw.startswith("'") and raw.endswith("'")) or (
        raw.startswith('"') and raw.endswith('"')
    ):
        return raw[1:-1].replace("\\'", "'").replace('\\"', '"')
    # Bool
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    # Int
    try:
        return int(raw)
    except ValueError:
        pass
    # Float
    try:
        return float(raw)
    except ValueError:
        pass
    raise WorkflowConditionError(f"Cannot parse value: {raw!r}")


def _split_top_level(s: str, sep: str) -> list[str]:
    """Split by sep only at top level (ignore inside quotes/brackets)."""
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    in_quote = None
    i = 0
    while i < len(s):
        c = s[i]
        if in_quote:
            if c == in_quote and (i == 0 or s[i - 1] != "\\"):
                in_quote = None
            current.append(c)
        elif c in ("'", '"'):
            in_quote = c
            current.append(c)
        elif c in ("[", "(", "{"):
            depth += 1
            current.append(c)
        elif c in ("]", ")", "}"):
            depth -= 1
            current.append(c)
        elif depth == 0 and s[i : i + len(sep)] == sep:
            parts.append("".join(current))
            current = []
            i += len(sep) - 1
        else:
            current.append(c)
        i += 1
    parts.append("".join(current))
    return parts


def evaluate_condition(expression: str, context: WorkflowContext) -> bool:
    """
    Parse expressions of the form: steps.<id>.<field> <op> <value>
    Supported ops: ==, !=, >, <, >=, <=, in, not in
    On missing step/field: return False (conservative — skip rather than crash).
    On parse error: raise WorkflowConditionError.
    """
    expression = expression.strip()
    if not expression:
        raise WorkflowConditionError("Empty condition expression")

    m = _EXPR_PATTERN.match(expression)
    if not m:
        raise WorkflowConditionError(
            f"Condition must match: steps.<step_id>.<field> <op> <value>. Got: {expression!r}"
        )

    step_id, field, op, value_str = m.group(1), m.group(2), m.group(3), m.group(4)
    op = op.lower().replace(" ", "")

    left = context.get_field(step_id, field)
    # Missing step or field → conservative False
    if left is None:
        return False

    try:
        right = _parse_value(value_str)
    except WorkflowConditionError:
        raise

    # Type coercion for comparison: if right is int/float and left is str, try to coerce left
    if isinstance(right, (int, float)) and isinstance(left, str):
        try:
            if isinstance(right, int):
                left = int(left)
            else:
                left = float(left)
        except (ValueError, TypeError):
            pass
    if isinstance(right, bool) and isinstance(left, str):
        left = left.lower() in ("true", "1", "yes")

    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == ">":
        return left > right  # type: ignore[return-value]
    if op == "<":
        return left < right  # type: ignore[return-value]
    if op == ">=":
        return left >= right  # type: ignore[return-value]
    if op == "<=":
        return left <= right  # type: ignore[return-value]
    if op == "in":
        if not isinstance(right, (list, tuple, str)):
            raise WorkflowConditionError(f"Right side of 'in' must be list or str, got {type(right)}")
        return left in right  # type: ignore[operator]
    if op == "notin":
        if not isinstance(right, (list, tuple, str)):
            raise WorkflowConditionError(
                f"Right side of 'not in' must be list or str, got {type(right)}"
            )
        return left not in right  # type: ignore[operator]

    raise WorkflowConditionError(f"Unsupported operator: {op!r}")
