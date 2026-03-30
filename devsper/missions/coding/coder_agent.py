from devsper.missions.base_agent import MissionAgent


class CoderAgent(MissionAgent):
    def __init__(self, model_name: str = "auto") -> None:
        super().__init__(
            name="coder_agent",
            role_prompt="You are a coder agent. Implement working, maintainable code.",
            model_name=model_name,
        )
