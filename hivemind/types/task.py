from enum import Enum
from pydantic import BaseModel

class TaskStatus(Enum):
    PENDING = 0
    RUNNING = 1
    COMPLETED = 2
    FAILED = -1
    

class Task(BaseModel):
    id: str
    description: str
    dependencies: list[str]= []
    status: TaskStatus = TaskStatus.PENDING
    result: str | None = None
