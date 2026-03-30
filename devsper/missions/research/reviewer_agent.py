from devsper.missions.base_agent import MissionAgent


class ReviewerAgent(MissionAgent):
    def __init__(self, model_name: str = "auto") -> None:
        super().__init__(
            name="reviewer_agent",
            role_prompt="You are a reviewer agent. Critique logic, evidence quality, and gaps.",
            model_name=model_name,
        )
