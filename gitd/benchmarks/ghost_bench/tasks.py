"""Ghost Bench task loading — reads task definitions from task_data/*.json."""

from pathlib import Path

from gitd.benchmarks.base import Task, load_tasks_from_dir

TASK_DATA_DIR = Path(__file__).parent / "task_data"
SUITE_NAME = "ghost_bench"


def load_tasks(category: str | None = None) -> list[Task]:
    return load_tasks_from_dir(TASK_DATA_DIR, category)


def get_task(task_id: str) -> Task | None:
    for task in load_tasks():
        if task.id == task_id:
            return task
    return None


def list_task_ids() -> list[str]:
    return [t.id for t in load_tasks()]
