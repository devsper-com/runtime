from devsper.missions.base_agent import MissionAgent


class WriterAgent(MissionAgent):
    def __init__(self, model_name: str = "auto") -> None:
        super().__init__(
            name="writer_agent",
            role_prompt="You are a writer agent. Improve structure, clarity, and depth.",
            model_name=model_name,
        )
