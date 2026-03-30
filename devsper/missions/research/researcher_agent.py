from devsper.missions.base_agent import MissionAgent


class ResearcherAgent(MissionAgent):
    def __init__(self, model_name: str = "auto") -> None:
        super().__init__(
            name="researcher_agent",
            role_prompt="You are a researcher agent. Gather evidence, references, and key findings.",
            model_name=model_name,
        )
