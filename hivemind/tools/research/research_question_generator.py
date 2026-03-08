"""Generate simple research questions from a topic (template-based, no LLM)."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class ResearchQuestionGeneratorTool(Tool):
    """Generate example research questions for a topic using fixed templates."""

    name = "research_question_generator"
    description = "Generate sample research questions for a topic (template-based)."
    input_schema = {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Research topic or domain"},
            "count": {"type": "integer", "description": "Number of questions (default 3)"},
        },
        "required": ["topic"],
    }

    def run(self, **kwargs) -> str:
        topic = kwargs.get("topic")
        count = kwargs.get("count", 3)
        if not topic or not isinstance(topic, str):
            return "Error: topic must be a non-empty string"
        if not isinstance(count, int) or count < 1:
            count = 3
        templates = [
            f"What are the main challenges in {topic}?",
            f"How has {topic} evolved in recent years?",
            f"What are the best practices for applying {topic}?",
            f"What is the relationship between {topic} and related fields?",
            f"What open problems remain in {topic}?",
        ]
        chosen = templates[: min(count, len(templates))]
        return "Suggested research questions:\n" + "\n".join(f"- {q}" for q in chosen)


register(ResearchQuestionGeneratorTool())
