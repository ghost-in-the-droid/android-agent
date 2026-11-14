"""Run each showcase action from independently reset and explicitly seeded state.

Use only with an operator-approved private session JSON. No device is chosen automatically.
Raw captures, inventories and transport settings stay outside tracked files.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from gitd.bots.common.adb import Device
from gitd.skills.engine.context import RunContext
from gitd.skills.engine.evidence import collect_fingerprint, write_evidence
from gitd.skills.engine.loader import load_skill
from gitd.skills.engine.pyimport import CTX_SKILL_KEY, ident_for_skill
from gitd.skills.engine.runner import _run_step, run_action
from tools.showcase_replay import CLOCK, DemoReplay, ReplayCase, ResetRefused

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = "/sdcard/Documents/Markor"
NOTE_TITLE = "Isolated Shopping"
NOTE_BODY = "Milk\nEggs"
TASK_TITLE = "Isolated buy stamps"
ALARM_LABEL = "Isolated demo alarm"


def helper(ref):
    spec = importlib.util.spec_from_file_location(
        "showcase_" + ref.replace("/", "_"), ROOT / "skillhub" / ref / "helpers.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def initialize(skill, device, subroutine):
    ctx = RunContext(action_name="fixture_setup", device_serial=device.serial)
    ctx.extras.update(
        {
            "_skill_popup_detectors": skill.popup_detectors,
            "_os_popup_policy": skill.os_popup_policy,
            "_current_skill_dir": str(skill.skill_dir),
            CTX_SKILL_KEY: ident_for_skill(skill),
        }
    )
    _run_step({"subroutine": subroutine}, ctx, device, [], True)


def checked_seed(skill, action, params, device):
    result = run_action(skill, action, params=params, device_serial=device.serial)
    if not result.success:
        raise ResetRefused(f"Seed action {action} failed: {result.error}")
    return result.data


def tap(device, node):
    a, b, c, d = node["bounds"]
    device.tap((a + c) // 2, (b + d) // 2)
    time.sleep(0.5)


def reset_clock_ui(device):
    """System Clock: delete only named test alarms; reset timers/stopwatch in UI.

    Requires the explicitly authorized fleet snapshot window. The harness stops
    rather than deleting an unknown enabled alarm or timer.
    """
    h = helper("ghost/clock")
    skill = load_skill(ROOT / "skillhub/ghost/clock")
    for _ in range(15):
        # A tab switch can briefly yield a tree without its alarm cards. Do not
        # interpret that transient absence as successful cleanup: independently
        # list the persisted UI rows, then locate the known test card afresh.
        alarms = checked_seed(skill, "list_alarms", {}, device)["alarms"]
        if any(a["enabled"] and not a["label"].startswith("Isolated ") for a in alarms):
            raise ResetRefused("Unknown enabled alarm; refusing deletion")
        if not any(a["label"].startswith("Isolated ") for a in alarms):
            break
        nodes = h.clock_snapshot(device)
        labels = [n for n in nodes if n["id"] == h._ID + "label" and n["text"].startswith("Isolated ")]
        if not labels:
            time.sleep(0.5)
            continue
        label = labels[0]
        cards = [
            c
            for c in nodes
            if h._inside(label["bounds"], c["bounds"])
            and any(n["id"] == h._ID + "onoff" and h._inside(n["bounds"], c["bounds"]) for n in nodes)
        ]
        if not cards:
            raise ResetRefused("Known test alarm has no unambiguous card")
        card = min(cards, key=lambda n: (n["bounds"][2] - n["bounds"][0]) * (n["bounds"][3] - n["bounds"][1]))
        expand = next(
            (n for n in nodes if n["desc"] == "Expand alarm" and h._inside(n["bounds"], card["bounds"])), None
        )
        if expand:
            tap(device, expand)
        deletes = [n for n in h.clock_snapshot(device) if n["desc"] == "Delete" or n["text"] == "Delete"]
        if len(deletes) != 1:
            raise ResetRefused("Cannot identify one test alarm delete button")
        tap(device, deletes[0])
    else:
        raise ResetRefused("Known test alarms did not disappear within reset bound")
    for _ in range(12):
        prefs = h._clock_prefs(device)
        labels = [v for k, v in prefs.items() if k.startswith("timer_label_")]
        if not labels:
            break
        if any(not v.startswith("Isolated ") for v in labels):
            raise ResetRefused("Unknown pre-existing timer; refusing deletion")
        nodes = h.show_clock_tab(device, "timer")
        deletes = [n for n in nodes if n["desc"] == "Delete"]
        if not deletes:
            raise ResetRefused("Timer delete control absent")
        tap(device, deletes[0])
    else:
        raise ResetRefused("Too many timers")
    nodes = h.show_clock_tab(device, "stopwatch")
    pause = next((n for n in nodes if n["desc"] == "Pause"), None)
    if pause:
        tap(device, pause)
        nodes = h.clock_snapshot(device)
    reset = next((n for n in nodes if n["desc"] == "Reset" or n["text"] == "Reset"), None)
    if reset:
        tap(device, reset)
        nodes = h.clock_snapshot(device)
    digits = [
        n["text"] for n in nodes if n["id"] in (h._ID + "stopwatch_time_text", h._ID + "stopwatch_hundredths_text")
    ]
    if not digits or any(any(c not in "0:" for c in value) for value in digits):
        raise ResetRefused("Stopwatch is not visibly reset to zero")
    if not any(n["desc"] == "Start" for n in nodes):
        raise ResetRefused("Stopwatch is not stopped")
    return {
        "verified": True,
        "alarms": alarms,
        "timers": 0,
        "stopwatch": "zero, stopped",
        "limitation": "System Clock retains disabled factory alarms and unrelated cities; no pm clear",
    }


class Fixtures:
    def __init__(self, device, output, notebook_authorized):
        self.device, self.output = device, output
        self.notebook_authorized = notebook_authorized

    def clean_notebook(self):
        if not self.notebook_authorized:
            raise ResetRefused("External notebook reset has not been authorized/backed up")
        self.device.adb("shell", "rm", "-rf", NOTEBOOK)
        self.device.adb("shell", "mkdir", "-p", NOTEBOOK)
        if self.device.adb("shell", "ls", "-A", NOTEBOOK):
            raise ResetRefused("External notebook is not empty")

    def file(self, name, content):
        path = self.output / name
        path.write_text(content)
        remote = NOTEBOOK + "/" + name
        self.device.adb("push", str(path), remote)
        if self.device.adb("shell", shlex.join(["cat", remote])) != content.strip():
            raise ResetRefused("Seed file readback differs")
        return {"file": name, "sha256": hashlib.sha256(content.encode()).hexdigest()}

    def seed(self, case, skill):
        d = self.device
        fixture = {"verified": True, "setup": [], "seed": "none"}
        if case.package == "org.fossify.math":
            # The data-clear establishes an empty display/history. Only read
            # actions receive the named calculation, independently each time.
            if case.action == "get_history":
                result = checked_seed(skill, "calculate", {"expression": "12*3"}, d)
                assert result["value"] == 36
                fixture["seed"] = "one calculation: 12*3 = 36"
        elif case.package == CLOCK:
            if case.action == "list_alarms":
                checked_seed(skill, "set_alarm", {"hour": 7, "minute": 30, "label": ALARM_LABEL}, d)
                fixture["seed"] = "one enabled 07:30 alarm: " + ALARM_LABEL
            elif case.action == "add_world_city":
                nodes = helper("ghost/clock").show_clock_tab(d, "clock")
                if any(
                    n["id"].endswith(":id/city_name") and case.params["city"].lower() in n["text"].lower()
                    for n in nodes
                ):
                    raise ResetRefused("Target city already exists; would be a no-op")
                fixture["target_city_absent"] = True
        elif case.package == "net.gsantner.markor":
            self.clean_notebook()
            d.adb("shell", "appops", "set", "net.gsantner.markor", "MANAGE_EXTERNAL_STORAGE", "allow")
            initialize(skill, d, "open_markor")
            self.clean_notebook()  # First-run sample files are not test fixtures.
            fixture["setup"] = ["first-run intro", "demo app all-files permission", "empty external notebook"]
            if case.action in ("read_note", "list_notes"):
                fixture["seed"] = self.file(NOTE_TITLE + ".md", NOTE_BODY)
        elif case.package == "org.tasks":
            empty = checked_seed(skill, "list_tasks", {}, d)
            if empty["tasks"]:
                raise ResetRefused("Fresh Tasks local list is not empty")
            fixture["setup"] = ["first-run local-only mode; no sync", "verified empty list"]
            if case.action != "add_task":
                checked_seed(skill, "add_task", {"title": TASK_TITLE}, d)
                data = checked_seed(skill, "list_tasks", {}, d)
                if [t["title"] for t in data["tasks"]] != [TASK_TITLE]:
                    raise ResetRefused("Expected exactly one seeded open task")
                fixture["seed"] = "one open task: " + TASK_TITLE
        elif case.package == "com.arduia.expense":
            initialize(skill, d, "open_pro_expense")
            fixture["setup"] = ["first-run language/currency pages only; no expense writes"]
            # Empty UI must be independently verified even without SQLite.
            h = helper("androidworld/pro-expense")
            nodes = h.nodes(d, native=True)
            self.output.joinpath("expense-empty-state.json").write_text(json.dumps(nodes, indent=2))
            if any(n["id"].endswith(":id/tv_expense_name") for n in nodes):
                raise ResetRefused("Expense entries unexpectedly exist after clear")
            try:
                rows = h.ledger(d)
            except RuntimeError:
                rows = None
            if rows:
                raise ResetRefused("Expense ledger is not empty")
            fixture["empty_ledger_checked"] = "sqlite" if rows is not None else "fresh pm clear + first-run setup"
            if case.action.endswith("from_markor"):
                self.clean_notebook()
                text = (
                    "name|amount_dollars|category_name|note\n"
                    "Demo train|8.50|Transportation|Client visit Reimbursable\n"
                    "Demo snack|2.00|Food|Personal demo\n"
                )
                fixture["seed"] = self.file("my_expenses.txt", text)
        return fixture


def verify_fixture_result(case, result):
    """Additional fixture-specific assertions, beyond the action's own validator."""
    if not result.success:
        return False
    data = result.data
    if case.skill == "ghost/calculator" and case.action == "read_result":
        return data.get("value") == 0
    if case.skill == "ghost/calculator" and case.action == "get_history":
        return data.get("results") == ["36"] and len(data.get("formulas", [])) == 1
    if case.skill == "ghost/markor" and case.action == "read_note":
        return data.get("content", "").strip() == NOTE_BODY
    if case.skill == "ghost/markor" and case.action == "list_notes":
        return data.get("files") == [NOTE_TITLE + ".md"] and data.get("folders") == []
    if case.skill == "ghost/tasks" and case.action in ("list_tasks", "search_tasks"):
        return [t["title"] for t in data.get("tasks", [])] == [TASK_TITLE]
    if case.skill == "ghost/clock" and case.action == "list_alarms":
        return sum(a["label"] == ALARM_LABEL and a["enabled"] for a in data.get("alarms", [])) == 1
    return True


@contextmanager
def recording(device, output):
    remote = "/sdcard/ghost-isolated-" + output.stem + ".mp4"
    command = shlex.join(["screenrecord", "--size", "324x720", "--bit-rate", "1500000", "--time-limit", "180", remote])
    process = subprocess.Popen(
        ["adb", "-s", device.serial, "shell", command + " & p=$!; echo $p; wait $p"],
        stdout=subprocess.PIPE,
        stderr=output.with_suffix(".capture.log").open("w"),
        text=True,
    )
    pid = process.stdout.readline().strip()
    if not pid.isdigit():
        raise ResetRefused("Recorder did not return its process id")
    time.sleep(0.5)
    try:
        device.adb("shell", "kill", "-0", pid)
        yield
    finally:
        expired = process.poll() is not None
        device.adb_soft("shell", "kill", "-2", pid)
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        try:
            device.adb("pull", remote, str(output))
        finally:
            device.adb_soft("shell", "rm", "-f", remote)
    if expired:
        raise ResetRefused("Recorder exited before the action finished; clip is not complete")
    if not output.exists() or output.stat().st_size < 1000:
        raise ResetRefused("Recording is absent or truncated")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()
    session = json.loads(args.session.read_text())
    if session.get("reset_authorized") is not True:
        raise ResetRefused("Session lacks explicit demo-reset authorization")
    if session["device_label"] == "samsung-a03s" and session.get("phone_go") is not True:
        raise ResetRefused("Samsung needs the explicit phone handoff/go")
    if session.get("adb_server_socket"):
        os.environ["ADB_SERVER_SOCKET"] = session["adb_server_socket"]
    if session.get("adb_path_prefix"):
        os.environ["PATH"] = session["adb_path_prefix"] + ":" + os.environ["PATH"]
    device = Device(session["serial"])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    protocol = DemoReplay(
        device,
        baseline_packages=session["baseline_packages"],
        installed_by_lane=session["installed_by_lane"],
        snapshot_reset_packages=session.get("snapshot_reset_packages", []),
        snapshot_name=session.get("snapshot_name"),
    )
    fixtures = Fixtures(device, output, session.get("notebook_reset_authorized") is True)
    rows = []
    for item in json.loads((ROOT / "tools/fixtures/showcase_replays.json").read_text()):
        if args.only and item["slug"] not in args.only and item["action"] not in args.only:
            continue
        skill = load_skill(ROOT / "skillhub" / item["skill"])
        case = ReplayCase(item["skill"], item["action"], item["package"], item["params"])
        row = {**item, "device": session["device_label"], "started_at": datetime.now(timezone.utc).isoformat()}
        try:

            def execute():
                return run_action(skill, case.action, params=case.params, device_serial=device.serial)

            protocol_result = protocol.run(
                case,
                seed=lambda: fixtures.seed(case, skill),
                execute=execute,
                capture=lambda: recording(device, output / (item["slug"] + "-" + case.action + ".mp4")),
                ui_reset=(lambda: reset_clock_ui(device))
                if case.package == CLOCK and session.get("system_clock_ui_reset")
                else None,
            )
            result = protocol_result.pop("result")
            verified = verify_fixture_result(case, result)
            row.update(protocol_result)
            row.update(
                success=result.success and verified,
                action_success=result.success,
                fixture_result_verified=verified,
                result=result.as_dict(),
            )
            fp = collect_fingerprint(
                skill, device.serial, session["fingerprint_directory"] + "/" + item["slug"] + ".json"
            )
            row["fingerprint"] = fp
            # Do not publish a success artifact when the fixture-specific oracle
            # rejected it; that would recreate the old misleading pass claim.
            if verified:
                row["artifact"] = str(
                    write_evidence(
                        skill,
                        [result],
                        fp,
                        login="ghost" if skill.author != "ghost" else None,
                        emulator=session["device_label"] != "samsung-a03s",
                    ).relative_to(ROOT)
                )
        except Exception as error:
            row.update(success=False, error_type=type(error).__name__, error=str(error), protocol=list(protocol.events))
        row["finished_at"] = datetime.now(timezone.utc).isoformat()
        rows.append(row)
        (output / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
        print(item["slug"], case.action, "PASS" if row["success"] else "FAIL", row.get("error", ""), flush=True)
    print("TOTAL", sum(r["success"] for r in rows), "/", len(rows), flush=True)


if __name__ == "__main__":
    main()
