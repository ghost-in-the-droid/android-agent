"""Tests for benchmark infrastructure."""

from gitd.benchmarks.base import Task, TaskResult, load_tasks_from_dir
from gitd.benchmarks.ghost_bench.tasks import TASK_DATA_DIR, get_task, list_task_ids, load_tasks


def test_load_tasks():
    tasks = load_tasks()
    assert len(tasks) >= 10
    assert all(isinstance(t, Task) for t in tasks)


def test_load_tasks_by_category():
    settings = load_tasks("settings")
    nav = load_tasks("navigation")
    assert all(t.category == "settings" for t in settings)
    assert all(t.category == "navigation" for t in nav)
    assert len(settings) + len(nav) == len(load_tasks())


def test_get_task():
    task = get_task("SystemWifiTurnOn")
    assert task is not None
    assert task.goal == "Turn wifi on."
    assert task.app == "com.android.settings"
    assert task.init["cmd"] == "svc wifi disable"


def test_get_task_not_found():
    assert get_task("NonExistent") is None


def test_list_task_ids():
    ids = list_task_ids()
    assert "SystemWifiTurnOn" in ids
    assert "OpenAppSettings" in ids


def test_task_max_steps():
    task = get_task("SystemAirplaneModeOn")
    assert task is not None
    assert task.complexity == 1.5
    assert task.max_steps == 15


def test_task_result_defaults():
    result = TaskResult(task_id="test", goal="test goal", model="m", device="d")
    assert result.score == 0.0
    assert result.error == ""
    assert result.agent_log == []


def test_load_tasks_from_dir():
    tasks = load_tasks_from_dir(TASK_DATA_DIR)
    assert len(tasks) == len(load_tasks())


def test_all_tasks_have_eval():
    for task in load_tasks():
        assert task.eval, f"Task {task.id} missing eval"
        assert task.eval.get("cmd"), f"Task {task.id} eval missing cmd"
