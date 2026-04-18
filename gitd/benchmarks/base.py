"""Base types for benchmark suites — shared across ghost_bench and future androidworld."""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Task:
    """A single benchmark task."""

    id: str
    goal: str
    app: str
    category: str
    complexity: float = 1.0
    init: dict = field(default_factory=dict)
    eval: dict = field(default_factory=dict)
    teardown: dict | None = None

    @property
    def max_steps(self) -> int:
        return int(self.complexity * 10)


@dataclass
class TaskResult:
    """Result of running a single task."""

    task_id: str
    goal: str
    model: str
    device: str
    score: float = 0.0
    reason: str = ""
    steps: int = 0
    time_s: float = 0.0
    agent_log: list = field(default_factory=list)
    error: str = ""


def load_tasks_from_dir(task_data_dir: Path, category: str | None = None) -> list[Task]:
    """Load tasks from all JSON files in a directory."""
    tasks = []
    if not task_data_dir.exists():
        return tasks
    for f in sorted(task_data_dir.glob("*.json")):
        for raw in json.loads(f.read_text()):
            task = Task(**raw)
            if category is None or task.category == category:
                tasks.append(task)
    return tasks
