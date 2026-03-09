"""Pydantic models for the workflow DSL."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OutputField(BaseModel):
    name: str
    type: Literal["str", "int", "float", "bool", "list", "dict"]
    description: str | None = None
    required: bool = True


class StepCondition(BaseModel):
    """Evaluated as: steps.<step_id>.<field> <op> <value>."""

    expression: str  # e.g. "steps.classify.category == 'technical'"


class WorkflowStep(BaseModel):
    id: str  # unique within workflow, used for references
    task: str  # prompt/task description (supports {var} interpolation)
    depends_on: list[str] = []  # step ids this step waits for
    if_: StepCondition | None = Field(None, alias="if")  # skip step if false
    output_schema: list[OutputField] = []  # if set, agent must return structured JSON
    role: str | None = None
    model: str | None = None  # override worker model for this step
    retry: int = 0  # number of retries on failure
    timeout_seconds: int | None = None

    model_config = ConfigDict(populate_by_name=True)


class WorkflowDefinition(BaseModel):
    name: str
    description: str | None = None
    version: str = "1.0"
    steps: list[WorkflowStep]
    inputs: list[OutputField] = []  # required inputs passed at runtime

    @model_validator(mode="after")
    def validate_step_ids_unique(self) -> "WorkflowDefinition":
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            seen: set[str] = set()
            for i in ids:
                if i in seen:
                    raise ValueError(f"Duplicate step id: {i}")
                seen.add(i)
        return self

    @model_validator(mode="after")
    def validate_depends_on_references(self) -> "WorkflowDefinition":
        step_ids = {s.id for s in self.steps}
        for s in self.steps:
            for dep in s.depends_on:
                if dep not in step_ids:
                    raise ValueError(
                        f"Step {s.id!r} depends_on unknown step {dep!r}. "
                        f"Valid ids: {sorted(step_ids)}"
                    )
        return self
