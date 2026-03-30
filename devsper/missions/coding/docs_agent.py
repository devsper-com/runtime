from devsper.missions.base_agent import MissionAgent


class DocsAgent(MissionAgent):
    def __init__(self, model_name: str = "auto") -> None:
        super().__init__(
            name="docs_agent",
            role_prompt="You are a docs agent. Produce clear setup, usage, and maintenance docs.",
            model_name=model_name,
        )
