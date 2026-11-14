"""Clock skill helpers: read alarm rows and world-clock cities from the a11y tree.

Signature for python_action targets: (device, params, context) -> dict.
The deskclock tab pager keeps neighbouring tabs in the tree with off-screen
bounds, so every reader here keeps only nodes that are actually on screen.
"""

from __future__ import annotations

import re
import shlex
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

_ID = "com.google.android.deskclock:id/"
_SAMSUNG = "com.sec.android.app.clockpackage"
_TIME = re.compile(r"(\d{1,2}):(\d{2})\s*([AaPp][Mm])?")


def visible_nodes(device) -> list[dict]:
    """Flatten the current screen into on-screen nodes: text, desc, id, bounds, checked."""
    if getattr(device, "serial", None) and not getattr(device, "is_fake", False):
        return clock_snapshot(device)
    out: list[dict] = []
    tree = device.dump_portal_json() if hasattr(device, "dump_portal_json") else None
    if tree:
        stack = list(tree) if isinstance(tree, list) else [tree]
        while stack:
            n = stack.pop()
            b = n.get("boundsInScreen") or {}
            box = (b.get("left", 0), b.get("top", 0), b.get("right", 0), b.get("bottom", 0))
            if box[2] > box[0] and box[3] > box[1] and box[0] >= 0:
                out.append(
                    {
                        "text": n.get("text") or "",
                        "desc": n.get("contentDescription") or "",
                        "id": n.get("resourceId") or "",
                        "bounds": box,
                        "checked": bool(n.get("isChecked")),
                    }
                )
            stack.extend(reversed(n.get("children") or []))
        out.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
        return out
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append(
                {
                    "text": a.get("text", ""),
                    "desc": a.get("content-desc", ""),
                    "id": a.get("resource-id", ""),
                    "bounds": tuple(nums),
                    "checked": a.get("checked") == "true",
                }
            )
    return out


def to_24h(text: str) -> str | None:
    """'7:30 AM' -> '07:30'; '19:05' -> '19:05'."""
    m = _TIME.search(text.replace(" ", " ").replace("\xa0", " "))
    if not m:
        return None
    h, mins, ampm = int(m.group(1)), m.group(2), (m.group(3) or "").upper()
    if ampm == "PM" and h != 12:
        h += 12
    elif ampm == "AM" and h == 12:
        h = 0
    return f"{h:02d}:{mins}"


def _inside(inner, outer) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def read_alarm_rows(device) -> list[dict]:
    nodes = visible_nodes(device)
    clocks = [n for n in nodes if n["id"] == _ID + "digital_clock"]
    # Alarm cards: wide, id-less containers. Their content-desc is "<time> <label>",
    # but freshly added cards can report only " <label>", so match by containment.
    cards = sorted(
        [n for n in nodes if not n["id"] and n["desc"]],
        key=lambda n: (n["bounds"][2] - n["bounds"][0]) * (n["bounds"][3] - n["bounds"][1]),
    )
    rows = []
    for clock in clocks:
        card = next(
            (
                c
                for c in cards
                if _inside(clock["bounds"], c["bounds"])
                and any(n["id"] == _ID + "onoff" and _inside(n["bounds"], c["bounds"]) for n in nodes)
            ),
            None,
        )
        if card is None:
            continue
        inside = [n for n in nodes if _inside(n["bounds"], card["bounds"])]
        label = next((n["text"] for n in inside if n["id"] == _ID + "label"), "")
        days = next(
            (n["text"] for n in inside if n["id"] in (_ID + "days_of_week", _ID + "upcoming_instance_label")), ""
        )
        switch = next((n for n in inside if n["id"] == _ID + "onoff"), None)
        rows.append(
            {
                "time": to_24h(clock["text"] or clock["desc"]),
                "label": label or "Alarm",
                "repeat": days,
                "enabled": bool(switch and switch["checked"]),
            }
        )
    return rows


def list_alarms(device, params, context):
    """Collect every alarm on the Alarm tab, scrolling until no new rows appear."""
    seen: dict[tuple, dict] = {}
    for _ in range(6):
        before = len(seen)
        for row in read_alarm_rows(device):
            seen.setdefault((row["time"], row["label"], row["repeat"]), row)
        if len(seen) == before and before:
            break
        scroll_alarms(device)
    for _ in range(3):
        scroll_alarms(device, down=False)
    alarms = sorted(seen.values(), key=lambda r: r["time"] or "")
    return {"success": True, "data": {"alarms": alarms, "count": len(alarms)}}


def scroll_alarms(device, down=True):
    nodes = visible_nodes(device)
    if not nodes:
        return
    width = max(n["bounds"][2] for n in nodes)
    height = max(n["bounds"][3] for n in nodes)
    top, bottom = int(height * 0.3), int(height * 0.7)
    device.swipe(width // 2, bottom if down else top, width // 2, top if down else bottom, 300)


def list_world_cities(device, params, context):
    nodes = visible_nodes(device)
    cities = [n["text"] for n in nodes if n["id"] == _ID + "city_name" and n["text"]]
    offsets = [n["desc"] or n["text"] for n in nodes if n["id"] == _ID + "hours_ahead"]
    return {
        "success": True,
        "data": {"cities": [{"city": c, "offset": o} for c, o in zip(cities, offsets + [""] * len(cities))]},
    }


# ── End-state validators: (device, context) -> bool ──────────────────────────


def alarm_exists(device, context) -> bool:
    want = f"{int(context.params['hour']):02d}:{int(context.params['minute']):02d}"
    label = str(context.params.get("label") or "").strip()
    import time

    found = None
    # Alarms are sorted by time, so a new one can be below the fold: scroll down, then back.
    for attempt in range(8):
        rows = read_alarm_rows(device)
        found = next(
            (r for r in rows if r["time"] == want and r["enabled"] and (not label or r["label"] == label)), None
        )
        if found:
            break
        if attempt == 0:
            time.sleep(1.0)  # the new card can render a moment after the tab switch
        else:
            scroll_alarms(device)
            time.sleep(0.8)
    context.result["alarm"] = found
    return found is not None


def alarms_listed(device, context) -> bool:
    if not any(n["desc"] == "Add alarm" for n in visible_nodes(device)):
        return False
    alarms = context.result.get("alarms")
    for _ in range(6):
        scroll_alarms(device, down=False)
    fresh = list_alarms(device, {}, context)["data"]
    return (
        isinstance(alarms, list)
        and all(a.get("time") for a in alarms)
        and alarms == fresh["alarms"]
        and context.result.get("count") == fresh["count"]
    )


def timer_running(device, context) -> bool:
    if context.result.get("clock_package") == _SAMSUNG:
        if context.result.get("timer_setup_seconds") != int(context.params["seconds"]):
            return False
        for _ in range(10):
            if samsung_timer_active(device):
                return any(n["text"] == "Pause" or n["desc"] == "Pause"
                           for n in clock_snapshot(device, _SAMSUNG))
            time.sleep(.15)
        return False
    prefs = _clock_prefs(device)
    for key, state in prefs.items():
        if key.startswith("timer_state_") and state == "1":
            suffix = key.removeprefix("timer_state_")
            if prefs.get("timer_label_" + suffix, "") == str(context.params.get("label", "Timer")) and prefs.get(
                "timer_original_timet_" + suffix
            ) == str(int(context.params["seconds"]) * 1000):
                return True
    if prefs:
        return False
    nodes = show_clock_tab(device, "timer")
    first = None
    for _ in range(8):
        first = timer_ui_state(nodes, context.params)
        if first is not None:
            break
        viewport = next((n for n in nodes if n["id"] == _ID + "timer_view"), None)
        if viewport is None:
            return False
        left, top, right, bottom = viewport["bounds"]
        device.swipe(
            (left + right) // 2,
            int(top + 0.8 * (bottom - top)),
            (left + right) // 2,
            int(top + 0.2 * (bottom - top)),
            300,
        )
        nodes = clock_snapshot(device)
    if first is None:
        return False
    time.sleep(1.1)
    second = timer_ui_state(clock_snapshot(device), context.params)
    elapsed = time.monotonic() - getattr(context, "timer_started_at", time.monotonic())
    return (
        second is not None
        and 0 < second < first <= int(context.params["seconds"])
        and (first >= max(1, int(context.params["seconds"]) - elapsed - 5))
    )


def remember_timer_start(device, params, context):
    context.timer_started_at = time.monotonic()
    return {"success": True}


def clock_package(device, app="auto"):
    choices = {"samsung": _SAMSUNG, "google": "com.google.android.deskclock"}
    names = [app] if app != "auto" else ["samsung", "google"]
    for name in names:
        package = choices.get(name)
        if not package:
            continue
        try:
            if (device.adb("shell", "pm", "path", package) or "").startswith("package:"):
                return package
        except RuntimeError:
            continue
    return None


def samsung_timer_active(device):
    output = device.adb("shell", "dumpsys", "activity", "services", _SAMSUNG) or ""
    return any(("TimerService" in part or "TimerNotificationService" in part or "TimerAlarmService" in part) and "isForeground=true" in part
               for part in output.split("* ServiceRecord"))


def timer_picker(nodes):
    fields = sorted((n for n in nodes if n["id"] == _SAMSUNG + ":id/numberpicker_input"),
                    key=lambda n: n["bounds"][0])
    if len(fields) != 3:
        return None
    explicit = [int(m.group()) if (m := re.match(r"\d+", n["text"])) else None for n in fields]
    summaries = [n.get("desc", "") for n in nodes if n["id"] == _SAMSUNG + ":id/timer_picker_view"]
    if summaries:
        if len(summaries) != 1:
            return None
        match = re.fullmatch(r"(\d+) Hours?\s+(\d+) Minutes?\s+(\d+) Seconds?", summaries[0])
        if not match:
            return None
        values = list(map(int, match.groups()))
        if any(value is not None and value != summary for value, summary in zip(explicit, values)):
            return None
    else:
        if any(value is None for value in explicit):
            return None
        values = explicit
    if not (0 <= values[0] < 100 and 0 <= values[1] < 60 and 0 <= values[2] < 60):
        return None
    return fields, values


def _ready_samsung_picker(device, timeout=5):
    """Let a newly opened wheel settle before injecting its first input."""
    deadline = time.monotonic() + timeout
    previous = None
    while time.monotonic() < deadline:
        nodes = clock_snapshot(device, _SAMSUNG)
        picker = timer_picker(nodes)
        if picker is not None:
            fields, values = picker
            state = (tuple(values), tuple(n['bounds'] for n in fields))
            if state == previous:
                return nodes, fields, values
            previous = state
        else:
            previous = None
        time.sleep(.15)
    return None


def _samsung_picker_after_step(device, before, expected, timeout=3):
    """Observe one exact step; never issue a second tap to compensate blindly."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        nodes = clock_snapshot(device, _SAMSUNG)
        picker = timer_picker(nodes)
        if picker is not None:
            fields, values = picker
            if values == expected:
                return nodes, fields, values
            if values != before:
                return None
        time.sleep(.15)
    return None


def start_timer(device, params, context):
    seconds = int(params["seconds"])
    if not 1 <= seconds <= 86399:
        return {"success": False, "error": "seconds must be between 1 and 86399"}
    package = clock_package(device, str(params.get("app") or "auto"))
    if package is None:
        return {"success": False, "error": "No supported Clock app installed"}
    context.result["clock_package"] = package
    if package != _SAMSUNG:
        remember_timer_start(device, params, context)
        device.adb("shell", "am", "start", "-a", "android.intent.action.SET_TIMER", "-p", package,
                   "--ei", "android.intent.extra.alarm.LENGTH", str(seconds),
                   "--es", "android.intent.extra.alarm.MESSAGE", shlex.quote(str(params.get("label") or "Timer")),
                   "--ez", "android.intent.extra.alarm.SKIP_UI", "true")
        time.sleep(1.5)
        return {"success": True, "data": {"clock_package": package}}
    if str(params.get("label") or "Timer") != "Timer":
        return {"success": False, "error": "Samsung duration timers do not support a custom label in this action"}
    if samsung_timer_active(device):
        return {"success": False, "error": "Existing Samsung timer is active; left unchanged"}
    device.adb("shell", "am", "start", "-W", "-a", "android.intent.action.SHOW_TIMERS", "-p", package)
    picker = _ready_samsung_picker(device)
    if picker is None:
        return {"success": False, "error": "Samsung stopped Timer picker unavailable; no timer started"}
    nodes, fields, values = picker
    wanted = [seconds // 3600, seconds // 60 % 60, seconds % 60]
    for index, (target, modulus) in enumerate(zip(wanted, [100, 60, 60])):
        node, current = fields[index], values[index]
        forward, backward = (target - current) % modulus, (current - target) % modulus
        left, top, right, bottom = node["bounds"]
        # Samsung's NumberPicker +/- buttons lack stable IDs. Derive their
        # centres from the identified editable field, without opening a keyboard.
        y = bottom + (bottom - top) // 2 if forward <= backward else top - (bottom - top) // 2
        for _ in range(min(forward, backward)):
            expected = list(values)
            expected[index] = (values[index] + (1 if forward <= backward else -1)) % modulus
            device.tap((left + right) // 2, y, .25)
            updated = _samsung_picker_after_step(device, values, expected)
            if updated is None:
                return {"success": False, "error": "Samsung timer wheel did not settle at the requested step; no timer started"}
            nodes, fields, values = updated
    if values != wanted:
        return {"success": False, "error": "Samsung timer duration did not match; no timer started"}
    start = next((n for n in nodes if n["text"] == "Start" or n["desc"] == "Start"), None)
    if start is None:
        return {"success": False, "error": "Samsung Timer Start button missing"}
    context.result["timer_setup_seconds"] = seconds
    remember_timer_start(device, params, context)
    left, top, right, bottom = start["bounds"]
    device.tap((left + right) // 2, (top + bottom) // 2)
    return {"success": True, "data": {"clock_package": package, "timer_setup_seconds": seconds}}


def cancel_timer(device, params, context):
    package = clock_package(device, str(params.get("app") or "auto"))
    if package != _SAMSUNG:
        return {"success": False, "error": "cancel_timer currently supports Samsung Clock only"}
    # SHOW_TIMERS opens Samsung's add-timer picker even when another timer is
    # running. Read the visible active timer directly, without changing pages.
    nodes = clock_snapshot(device, package)
    # A generic Cancel/Dismiss/Stop may belong to a ringing alarm. The native
    # Timer-specific cancel ID and pause/resume companion establish this screen.
    timer_screen = any(n["id"] in (_SAMSUNG + ":id/timer_pause_button", _SAMSUNG + ":id/timer_resume_button") for n in nodes)
    button = next((n for n in nodes if timer_screen and n["id"] == _SAMSUNG + ":id/timer_cancel_button"
                   and (n["text"] == "Cancel" or n["desc"] == "Cancel")), None)
    if button is None:
        if not samsung_timer_active(device):
            return {"success": True, "data": {"clock_package": package, "running": False}}
        return {"success": False, "error": "Samsung timer cancellation control unavailable"}
    left, top, right, bottom = button["bounds"]
    device.tap((left + right) // 2, (top + bottom) // 2)
    for _ in range(20):
        if not samsung_timer_active(device):
            return {"success": True, "data": {"clock_package": package, "running": False}}
        time.sleep(.2)
    return {"success": False, "error": "Samsung timer remains active"}


def get_timer_state(device, params, context):
    package = clock_package(device, str(params.get("app") or "auto"))
    if package != _SAMSUNG:
        return {"success": False, "error": "get_timer_state currently supports Samsung Clock only"}
    active = samsung_timer_active(device)
    return {"success": True, "data": {"clock_package": package, "active": active}}


def timer_cancelled(device, context):
    return (context.result.get("clock_package") == _SAMSUNG and context.result.get("running") is False
            and not samsung_timer_active(device))


def timer_state_matches(device, context):
    return (context.result.get("clock_package") == _SAMSUNG
            and context.result.get("active") == samsung_timer_active(device))


def clock_snapshot(device, package="com.google.android.deskclock"):
    """Read the active Clock window without waiting for animated widgets to idle.

    The bundled, reproducibly built JAR uses the platform UI Automator connection
    as the adb shell user. It refuses other apps and neither installs an APK nor
    reads private app files. Each invocation removes its temporary JAR.
    """
    remote = "/data/local/tmp/ghost-clock-" + uuid.uuid4().hex + ".jar"
    try:
        device.adb("push", str(Path(__file__).parent / "snapshot/clock-snapshot.jar"), remote)
        output = device.adb(
            "shell",
            "uiautomator",
            "runtest",
            "/system/framework/android.test.base.jar",
            remote,
            "-c",
            "ghost.clock.ClockSnapshot",
        )
        lines = [line.removeprefix("CLOCK_XML:") for line in output.splitlines() if line.startswith("CLOCK_XML:")]
        if len(lines) != 1:
            return []
        root = ET.fromstring(lines[0])
        window = next(root.iter("node"), None)
        if window is None:
            return []
        limits = tuple(map(int, re.findall(r"-?\d+", window.get("bounds", ""))))
        if len(limits) != 4:
            return []
        result = []
        for n in root.iter("node"):
            bounds = tuple(map(int, re.findall(r"-?\d+", n.get("bounds", ""))))
            if (
                len(bounds) == 4
                and bounds[2] > bounds[0] >= 0
                and bounds[3] > bounds[1] >= 0
                and _inside(bounds, limits)
                and n.get("package") == package
            ):
                result.append(
                    {
                        "id": n.get("resource-id", ""),
                        "text": n.get("text", ""),
                        "desc": n.get("content-desc", ""),
                        "bounds": bounds,
                        "checked": n.get("checked") == "true",
                    }
                )
        return result
    except (RuntimeError, OSError, ET.ParseError):
        return []
    finally:
        device.adb("shell", "rm", "-f", remote)


def show_clock_tab(device, tab):
    device.adb("shell", "am", "start", "-n", "com.google.android.deskclock/com.android.deskclock.DeskClock")
    for _ in range(4):
        nodes = clock_snapshot(device)
        target = next((n for n in nodes if n["id"] == _ID + "tab_menu_" + tab), None)
        if target:
            left, t, r, b = target["bounds"]
            device.tap((left + r) // 2, (t + b) // 2)
            return clock_snapshot(device)
        time.sleep(0.5)
    return []


def open_alarms(device, params, context):
    """Leave an animating timer/stopwatch without an idle-dependent tab lookup."""
    nodes = show_clock_tab(device, "alarm")
    return {"success": any(n["desc"] == "Add alarm" for n in nodes)}


def timer_ui_state(nodes, params):
    labels = [n for n in nodes if n["id"] == _ID + "timer_label" and n["text"] == str(params.get("label", "Timer"))]
    if len(labels) != 1:
        return None
    cards = [n for n in nodes if n["id"] == _ID + "timer_background" and _inside(labels[0]["bounds"], n["bounds"])]
    if cards:
        card = min(cards, key=lambda n: (n["bounds"][2] - n["bounds"][0]) * (n["bounds"][3] - n["bounds"][1]))
        nodes = [n for n in nodes if _inside(n["bounds"], card["bounds"])]
    elif sum(n["id"] == _ID + "timer_label" for n in nodes) != 1:
        return None
    if not any(n["id"] == _ID + "play_pause" and n["desc"] == "Pause" for n in nodes):
        return None
    values = [n["text"] for n in nodes if n["id"] == _ID + "timer_text"]
    if len(values) != 1 or not re.fullmatch(r"\d+(?::\d{2}){1,2}", values[0]):
        return None
    value = 0
    for part in values[0].split(":"):
        value = value * 60 + int(part)
    return value


def _clock_prefs(device):
    """Read persistent state without uiautomator's idle requirement. Root adb required."""
    try:
        xml = device.adb(
            "shell",
            "cat /data/user_de/0/com.google.android.deskclock/shared_prefs/com.google.android.deskclock_preferences.xml",
        )
        root = ET.fromstring(xml)
        if root.tag != "map":
            return {}
        return {n.get("name"): n.get("value", n.text or "") for n in root}
    except (ET.ParseError, RuntimeError, OSError, TypeError):
        return {}


def stopwatch_running(device, context) -> bool:
    prefs = _clock_prefs(device)
    if prefs:
        return prefs.get("sw_state") == "1"
    first = stopwatch_ui_state(clock_snapshot(device))
    if first is None:
        return False
    time.sleep(1.1)
    second = stopwatch_ui_state(clock_snapshot(device))
    return second is not None and second > first


def stopwatch_ui_state(nodes):
    if not any(n["desc"] == "Pause" for n in nodes):
        return None
    values = [n["text"] for n in nodes if n["id"] == _ID + "stopwatch_time_text"]
    if len(values) != 1:
        return None
    if not re.fullmatch(r"\d+(?::\d{2}){0,2}", values[0]):
        return None
    value = 0
    for part in values[0].split(":"):
        value = value * 60 + int(part)
    fractions = [n["text"] for n in nodes if n["id"] == _ID + "stopwatch_hundredths_text"]
    if len(fractions) != 1 or not re.fullmatch(r"\d{2}", fractions[0]):
        return None
    return value + int(fractions[0]) / 100


def start_stopwatch(device, params, context):
    """Already-running stopwatch is a no-op; no idle dump after tapping Start."""
    if stopwatch_running(device, context):
        return {"success": True}
    nodes = show_clock_tab(device, "stopwatch")
    if stopwatch_ui_state(nodes) is not None:
        return {"success": True}
    start = next((n for n in nodes if n["desc"] == "Start"), None)
    if start is None:
        return {"success": False, "error": "stopwatch Start control not visible"}
    left, t, r, b = start["bounds"]
    device.tap((left + r) // 2, (t + b) // 2)
    return {"success": True}


def clock_control(device, *, rid=None, desc=None):
    for _ in range(6):
        for node in clock_snapshot(device):
            if (rid is None or node["id"] == _ID + rid) and (desc is None or node["desc"] == desc):
                return node
        time.sleep(0.5)
    raise RuntimeError("Clock control not visible: " + str(rid or desc))


def tap_clock_control(device, **selector):
    node = clock_control(device, **selector)
    left, top, right, bottom = node["bounds"]
    device.tap((left + right) // 2, (top + bottom) // 2)


def add_world_city(device, params, context):
    from gitd.bots.common.adb import input_text_arg

    nodes = show_clock_tab(device, "clock")
    if not any(n["desc"] == "Add city" for n in nodes):
        return {"success": False, "error": "Clock city list not visible"}
    want = str(params["city"]).split(",")[0].strip().lower()
    if not want:
        return {"success": False, "error": "City must not be empty"}
    if any(n["id"] == _ID + "city_name" and want in n["text"].lower() for n in nodes):
        return {"success": True}
    tap_clock_control(device, desc="Add city")
    tap_clock_control(device, rid="open_search_view_edit_text")
    device.adb("shell", "input", "text", input_text_arg(str(params["city"])))
    tap_clock_control(device, rid="city_name")
    # An expiring timer can take over the Clock activity during selection.
    # Restore the city tab before independently validating the saved city.
    nodes = show_clock_tab(device, "clock")
    return {"success": any(n["desc"] == "Add city" for n in nodes)}


def city_listed(device, context) -> bool:
    want = str(context.params["city"]).split(",")[0].strip().lower()
    nodes = visible_nodes(device)
    if not any(n["desc"] == "Add city" for n in nodes):
        return False
    names = [n["text"] for n in nodes if n["id"].endswith("/city_name")]
    context.result["cities"] = names
    return any(want in n.lower() for n in names)
