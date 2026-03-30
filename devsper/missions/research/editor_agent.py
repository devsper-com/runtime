from devsper.missions.base_agent import MissionAgent


class EditorAgent(MissionAgent):
    def __init__(self, model_name: str = "auto") -> None:
        super().__init__(
            name="editor_agent",
            role_prompt="You are an editor agent. Finalize polished publication-ready output.",
            model_name=model_name,
        )
