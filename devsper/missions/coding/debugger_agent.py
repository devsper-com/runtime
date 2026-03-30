from devsper.missions.base_agent import MissionAgent


class DebuggerAgent(MissionAgent):
    def __init__(self, model_name: str = "auto") -> None:
        super().__init__(
            name="debugger_agent",
            role_prompt="You are a debugger agent. Diagnose failures and provide concrete fixes.",
            model_name=model_name,
        )
