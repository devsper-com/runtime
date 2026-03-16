"""Safely evaluate a mathematical expression (numbers and basic ops only)."""

import ast
import operator

from devsper.tools.base import Tool
from devsper.tools.registry import register


class CalculateExpressionTool(Tool):
    """Evaluate a safe math expression: numbers, +, -, *, /, **, parentheses. No names."""

    name = "calculate_expression"
    description = "Evaluate a mathematical expression. Only numbers and +, -, *, /, ** allowed."
    input_schema = {
        "type": "object",
        "properties": {"expression": {"type": "string", "description": "Math expression, e.g. 2 + 3 * 4"}},
        "required": ["expression"],
    }

    def run(self, **kwargs) -> str:
        expression = kwargs.get("expression")
        if not expression or not isinstance(expression, str):
            return "Error: expression must be a non-empty string"
        try:
            tree = ast.parse(expression, mode="eval")
            ops = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.Pow: operator.pow,
                ast.USub: operator.neg,
            }

            def eval_node(node):
                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                    return node.value
                if isinstance(node, ast.BinOp):
                    left = eval_node(node.left)
                    right = eval_node(node.right)
                    return ops[type(node.op)](left, right)
                if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
                    return -eval_node(node.operand)
                raise ValueError("Only numbers and +, -, *, /, ** allowed")
            result = eval_node(tree.body)
            return str(result)
        except (ValueError, SyntaxError, TypeError) as e:
            return f"Error: {e}"


register(CalculateExpressionTool())
