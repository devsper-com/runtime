"""
Multi-Model Council — draft-critique-synthesize execution for high-stakes subtasks.

Instead of routing a subtask to a single model, a council uses:
- Drafter (fast/cheap): produces an initial output
- Critic (strong/slow): reviews and identifies gaps or errors
- Synthesizer: combines draft + critique into a final answer

Applied selectively to subtasks above a complexity threshold.
"""

from devsper.council.council import Council, CouncilResult, CouncilConfig
from devsper.council.research_to_code import (
    ResearchHandoff,
    ResearchToCodeMission,
    ResearchToCodeResult,
)

__all__ = [
    "Council",
    "CouncilResult",
    "CouncilConfig",
    "ResearchHandoff",
    "ResearchToCodeMission",
    "ResearchToCodeResult",
]
