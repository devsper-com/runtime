"""
JSONL-backed eval dataset: load, save, and generate stub datasets.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from devsper.evals.types import EvalCase


class EvalDataset:
    """Ordered collection of EvalCases backed by a JSONL file."""

    def __init__(self, cases: list[EvalCase] | None = None, name: str = "dataset"):
        self.cases: list[EvalCase] = cases or []
        self.name = name

    def __len__(self) -> int:
        return len(self.cases)

    def __iter__(self):
        return iter(self.cases)

    def add(self, case: EvalCase) -> None:
        self.cases.append(case)

    def filter_by_role(self, role: str) -> "EvalDataset":
        return EvalDataset(
            [c for c in self.cases if c.role == role],
            name=f"{self.name}[{role}]",
        )

    @classmethod
    def load(cls, path: str | Path) -> "EvalDataset":
        """Load from a JSONL file. Each line is a JSON object (EvalCase dict)."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Dataset not found: {path}")
        cases = []
        with p.open() as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    d = json.loads(line)
                    if "id" not in d:
                        d["id"] = str(uuid.uuid4())[:8]
                    cases.append(EvalCase.from_dict(d))
                except json.JSONDecodeError as e:
                    raise ValueError(f"Bad JSON on line {i + 1} of {path}: {e}") from e
        return cls(cases, name=p.stem)

    def save(self, path: str | Path) -> None:
        """Write to a JSONL file (overwrites)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w") as f:
            for case in self.cases:
                f.write(json.dumps(case.to_dict()) + "\n")

    @classmethod
    def from_dicts(cls, records: list[dict], name: str = "dataset") -> "EvalDataset":
        cases = []
        for i, d in enumerate(records):
            if "id" not in d:
                d["id"] = str(i)
            cases.append(EvalCase.from_dict(d))
        return cls(cases, name=name)

    @classmethod
    def stub(cls, role: str = "general", n: int = 5) -> "EvalDataset":
        """Generate a minimal stub dataset for smoke-testing."""
        stubs = {
            "research": [
                ("What is transformer architecture?", "attention mechanism"),
                ("Summarize BERT vs GPT", "bidirectional"),
                ("What year was AlexNet published?", "2012"),
                ("Who invented backpropagation?", "Rumelhart"),
                ("What is RLHF?", "reinforcement learning from human feedback"),
            ],
            "code": [
                ("Write a Python function to reverse a string", "def"),
                ("What is a decorator in Python?", "wraps"),
                ("Implement binary search", "mid"),
                ("What does __init__ do?", "constructor"),
                ("How do you open a file in Python?", "open("),
            ],
            "analysis": [
                ("What is mean absolute error?", "absolute"),
                ("Explain p-value", "null hypothesis"),
                ("What is overfitting?", "training data"),
                ("Define precision and recall", "true positive"),
                ("What is cross-validation?", "fold"),
            ],
        }
        pairs = stubs.get(role, [
            (f"Task {i}", f"expected {i}") for i in range(n)
        ])[:n]
        cases = [
            EvalCase(id=str(i), task=t, expected=e, role=role)
            for i, (t, e) in enumerate(pairs)
        ]
        return cls(cases, name=f"stub_{role}")
