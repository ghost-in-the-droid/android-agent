"""Tests for benchmark infrastructure."""

from gitd.benchmarks.base import Task, TaskResult, load_tasks_from_dir
from gitd.benchmarks.ghost_bench.tasks import TASK_DATA_DIR, get_task, list_task_ids, load_tasks
import pytest
from fastapi.testclient import TestClient

from gitd.app import app
from gitd.benchmarks.ghost_bench import evaluators


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


def test_tasks_default_to_android_platform():
    task = Task(id="Sample", goal="Do a thing.", app="com.example", category="settings")
    assert task.supported_platforms() == ["android"]
    assert task.supports_platform("android")
    assert not task.supports_platform("ios")


def test_benchmark_tasks_api_exposes_platform_metadata():
    response = TestClient(app).get("/api/benchmarks/tasks")
    assert response.status_code == 200
    data = response.json()
    assert data
    first = data[0]
    assert first["platforms"] == ["android"]
    assert first["supports_android"] is True
    assert first["supports_ios"] is False


def test_benchmark_run_rejects_ios_for_android_only_tasks():
    response = TestClient(app).post(
        "/api/benchmarks/runs",
        json={
            "suite": "ghost_bench",
            "tasks": ["SystemWifiTurnOn"],
            "provider": "ollama",
            "model": "gemma3:4b",
            "device": "ios:abc123",
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "unsupported_platform"
    assert detail["platform"] == "ios"
    assert detail["device"] == "ios:abc123"
    assert detail["unsupported_tasks"] == ["SystemWifiTurnOn"]


def test_ghost_bench_evaluators_reject_ios_before_adb(monkeypatch):
    def fail_subprocess(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called for iOS refs")

    monkeypatch.setattr(evaluators.subprocess, "run", fail_subprocess)
    task = Task(
        id="Sample",
        goal="Do a thing.",
        app="com.android.settings",
        category="settings",
        init={"cmd": "svc wifi disable"},
    )

    with pytest.raises(RuntimeError, match="Android-only.*iOS"):
        evaluators.initialize_task(task, "ios:abc123")
