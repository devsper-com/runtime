from devsper.missions.base_agent import MissionAgent


class TesterAgent(MissionAgent):
    def __init__(self, model_name: str = "auto") -> None:
        super().__init__(
            name="tester_agent",
            role_prompt="You are a tester agent. Validate behavior and identify failing cases.",
            model_name=model_name,
        )
