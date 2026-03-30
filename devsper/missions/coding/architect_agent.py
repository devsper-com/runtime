from devsper.missions.base_agent import MissionAgent


class ArchitectAgent(MissionAgent):
    def __init__(self, model_name: str = "auto") -> None:
        super().__init__(
            name="architect_agent",
            role_prompt="You are an architect agent. Produce robust design and implementation plan.",
            model_name=model_name,
        )
