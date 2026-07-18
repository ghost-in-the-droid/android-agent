import json

from gitd.routers import explorer as explorer_router


class FakeProc:
    def poll(self):
        return None


def test_explorer_status_reads_ios_progress_metadata(monkeypatch, tmp_path):
    progress = {
        "device": "ios:abc123",
        "package": "com.google.chrome.ios",
        "platform": "ios",
        "output_dir": str(tmp_path),
        "current_activity": "com.google.chrome.ios",
        "states_found": 2,
        "max_states": 5,
        "transitions": 1,
        "current_depth": 1,
        "log_tail": ["state 2"],
    }
    (tmp_path / "progress.json").write_text(json.dumps(progress), encoding="utf-8")
    monkeypatch.setattr(
        explorer_router,
        "_active_proc",
        {
            "proc": FakeProc(),
            "pid": 1234,
            "package": "stale.package",
            "device": "ios:old",
            "platform": "android",
            "output_dir": str(tmp_path),
            "max_states": 5,
        },
    )

    status = explorer_router.explorer_status()

    assert status["running"] is True
    assert status["device"] == "ios:abc123"
    assert status["package"] == "com.google.chrome.ios"
    assert status["platform"] == "ios"
    assert status["output_dir"] == str(tmp_path)
    assert status["current_activity"] == "com.google.chrome.ios"
    assert status["states_found"] == 2
    assert status["transitions"] == 1
    assert status["log_tail"] == ["state 2"]


def test_explorer_runs_include_ios_platform(monkeypatch, tmp_path):
    run_dir = tmp_path / "com.google.chrome.ios"
    run_dir.mkdir()
    (run_dir / "state_graph.json").write_text(
        json.dumps(
            {
                "package": "com.google.chrome.ios",
                "device": "ios:abc123",
                "platform": "ios",
                "total_states": 2,
                "total_transitions": 1,
                "max_depth": 1,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(explorer_router, "_EXPLORER_DIR", tmp_path)

    runs = explorer_router.explorer_runs()

    assert runs == [
        {
            "name": "com.google.chrome.ios",
            "package": "com.google.chrome.ios",
            "states": 2,
            "transitions": 1,
            "max_depth": 1,
            "platform": "ios",
            "device": "ios:abc123",
            "date": runs[0]["date"],
        }
    ]
