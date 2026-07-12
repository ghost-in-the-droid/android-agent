#!/usr/bin/env python3
"""record_demo.py — "Ghost records Ghost": spec-driven showcase demo recorder.

Reads a demo definition (marketing copy from site/public/showcase/copy.yaml,
recording mechanics from site/public/showcase/<demo>/spec.yaml), records the
phone screen and the terminal simultaneously while executing the demo
timeline, then composites everything into a branded WebM:

    [ terminal (asciinema→agg) | phone-in-device-frame ]
    + burned captions + 1s intro card + 1s outro card

Outputs (only after the privacy OCR gate passes):
    site/public/showcase/<demo>/demo.webm
    site/public/showcase/<demo>/poster.png
    site/public/showcase/<demo>/snippet.py

Usage:
    python3 scripts/record_demo.py --demo langchain [--serial SERIAL]
    python3 scripts/record_demo.py --demo langchain --dry-run   # validate only
    python3 scripts/record_demo.py --list

Privacy: this script refuses to place any output into site/public/ unless the
rendered video passes an OCR scan against scripts/privacy/FORBIDDEN.txt (+
FORBIDDEN.local.txt). See scripts/privacy/RECORDING_CHECKLIST.md.

spec.yaml schema (recording mechanics; marketing copy lives in copy.yaml):

    demo: langchain                 # must match a copy.yaml id
    device: android                 # android | ios | both
    duration_target_s: 60
    platform_notes: ""              # free text, printed before recording
    record_size: null               # optional WxH for adb screenrecord --size
    setup:                          # device prep before recording starts
      - step: kill_all_apps
      - step: launch_app
        args: {package: com.sec.android.app.popupcalculator}
    timeline:                       # what happens while recording
      - t: 0
        caption: "One pip install gives your agent 40+ phone tools"
        action: terminal_type
        args: {cmd: "gitd doctor"}
      - t: 12
        action: phone_tap
        args: {x: 540, y: 1200}
      - t: 20
        action: wait_for_phone
        args: {seconds: 5}
    outro:
      cta_line: "pip install ghost-in-the-droid"
      cta_link: "https://ghostinthedroid.com"
    highlight_window: {start_s: 8, end_s: 15}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from privacy.scrub import (  # noqa: E402
    load_forbidden, scan_text, scrub_cast, scrub_text, scrubbed_env,
)

SHOWCASE_DIR = REPO_ROOT / "site" / "public" / "showcase"
BRAND_DIR = SHOWCASE_DIR / "_brand"

# ── Render constants ──────────────────────────────────────────────────────────
CANVAS_W, CANVAS_H = 1920, 1080
FPS = 30
INTRO_S = 1.0
OUTRO_S = 1.0
TERM_COLS, TERM_ROWS = 100, 24
TERM_X, TERM_W = 40, 1346          # 1346 = native agg width @ font 22 — the
                                   # terminal video is NEVER rescaled (sharpness)
TERM_Y = 256                       # video top; window chrome spans y 208-1034;
                                   # headline block lives at y 36-160 (C-prime-4)
FRAME_X_OFFSET = 689               # phone bezel right edge lands at x=1880 →
                                   # 40px right margin, matching the left margin
TYPE_DELAY_S = 0.005               # simulated keystroke interval — fast; long
                                   # CLI commands must not eat demo runtime
BG_HEX = "070a08"                  # canvas darker than the terminal body
                                   # (#0d130e) so the window separates

TIMELINE_ACTIONS = {
    "terminal_type", "terminal_exec", "wait_for_phone", "phone_tap",
    "phone_swipe", "phone_key", "phone_screenshot_pause", "sleep",
}
SETUP_STEPS = {"kill_all_apps", "wake_unlock", "launch_app", "clear_app",
               "install_apk", "shell"}
DEVICES = {"android", "ios", "both"}


def log(msg: str) -> None:
    print(f"[record_demo] {msg}", flush=True)


def die(msg: str) -> "NoReturn":  # noqa: F821
    print(f"[record_demo] ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def run(cmd: list[str], desc: str, heavy: bool = False, **kw) -> subprocess.CompletedProcess:
    """Run a pipeline tool, failing loudly. heavy=True runs under nice -19 so
    renders never starve the box."""
    if heavy:
        cmd = ["nice", "-n", "19"] + cmd
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        die(f"{desc} failed (exit {r.returncode}):\n{r.stderr[-2000:]}")
    return r


# ── Spec loading & validation ─────────────────────────────────────────────────

def load_copy() -> dict:
    copy_path = SHOWCASE_DIR / "copy.yaml"
    if not copy_path.exists():
        die(f"missing {copy_path} (marketing source of truth)")
    data = yaml.safe_load(copy_path.read_text())
    return {d["id"]: d for d in data.get("demos", [])}


def load_spec(demo: str) -> dict:
    """Join recording spec (spec.yaml) with marketing copy (copy.yaml)."""
    copy = load_copy()
    if demo not in copy:
        die(f"demo '{demo}' not found in copy.yaml (ids: {', '.join(sorted(copy))})")
    spec_path = SHOWCASE_DIR / demo / "spec.yaml"
    if not spec_path.exists():
        die(f"missing recording spec {spec_path}")
    spec = yaml.safe_load(spec_path.read_text())
    if not isinstance(spec, dict):
        die(f"{spec_path} is not a mapping")

    c = copy[demo]
    spec.setdefault("demo", demo)
    spec.setdefault("title", c.get("title", demo))
    spec["_copy"] = c
    if "outro" not in spec:
        ctas = c.get("ctas") or []
        spec["outro"] = {
            "cta_line": "pip install ghost-in-the-droid",
            "cta_link": ctas[0]["url"] if ctas else "https://ghostinthedroid.com",
        }
    return spec


def validate_spec(spec: dict) -> list[str]:
    """Return a list of validation errors (empty = valid)."""
    errs: list[str] = []
    demo = spec.get("demo", "")

    if spec.get("device") not in DEVICES:
        errs.append(f"device must be one of {sorted(DEVICES)}, got {spec.get('device')!r}")
    dur = spec.get("duration_target_s")
    if not isinstance(dur, (int, float)) or dur <= 0:
        errs.append("duration_target_s must be a positive number")

    timeline = spec.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        errs.append("timeline must be a non-empty list")
        timeline = []
    prev_t = -1.0
    for i, step in enumerate(timeline):
        where = f"timeline[{i}]"
        if not isinstance(step, dict):
            errs.append(f"{where}: not a mapping")
            continue
        t = step.get("t")
        if not isinstance(t, (int, float)) or t < 0:
            errs.append(f"{where}: t must be a non-negative number")
        elif t < prev_t:
            errs.append(f"{where}: t={t} goes backwards (prev {prev_t})")
        else:
            prev_t = float(t)
        action = step.get("action")
        if action not in TIMELINE_ACTIONS:
            errs.append(f"{where}: unknown action {action!r} (known: {sorted(TIMELINE_ACTIONS)})")
        args = step.get("args", {})
        if not isinstance(args, dict):
            errs.append(f"{where}: args must be a mapping")
            args = {}
        if action in ("terminal_type", "terminal_exec") and not args.get("cmd"):
            errs.append(f"{where}: {action} needs args.cmd")
        if action in ("wait_for_phone", "phone_screenshot_pause", "sleep") \
                and not isinstance(args.get("seconds"), (int, float)):
            errs.append(f"{where}: {action} needs numeric args.seconds")
        if action == "phone_tap" and not (
                isinstance(args.get("x"), (int, float)) and isinstance(args.get("y"), (int, float))):
            errs.append(f"{where}: phone_tap needs numeric args.x/args.y")
        if action == "phone_swipe" and not all(
                isinstance(args.get(k), (int, float)) for k in ("x1", "y1", "x2", "y2")):
            errs.append(f"{where}: phone_swipe needs numeric x1/y1/x2/y2")
        if action == "phone_key" and not args.get("key"):
            errs.append(f"{where}: phone_key needs args.key (e.g. KEYCODE_HOME)")
        cap = step.get("caption")
        if cap is not None and not isinstance(cap, str):
            errs.append(f"{where}: caption must be a string")

    for i, s in enumerate(spec.get("setup") or []):
        if not isinstance(s, dict) or s.get("step") not in SETUP_STEPS:
            errs.append(f"setup[{i}]: step must be one of {sorted(SETUP_STEPS)}")
        elif s["step"] == "launch_app" and not (s.get("args") or {}).get("package"):
            errs.append(f"setup[{i}]: launch_app needs args.package")

    env_extra = spec.get("env") or {}
    if not isinstance(env_extra, dict):
        errs.append("env must be a mapping of extra variables for demo commands")
    else:
        secret = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.I)
        for k, v in env_extra.items():
            if secret.search(str(k)) or scan_text(f"{k}={v}"):
                errs.append(f"env.{k}: secret-shaped or forbidden — demo env must be safe to show on screen")

    hw = spec.get("highlight_window")
    if not isinstance(hw, dict) or not all(
            isinstance(hw.get(k), (int, float)) for k in ("start_s", "end_s")):
        errs.append("highlight_window needs numeric start_s/end_s")
    else:
        length = hw["end_s"] - hw["start_s"]
        if length <= 0:
            errs.append("highlight_window end_s must be > start_s")
        elif not (4 <= length <= 10):
            errs.append(f"highlight_window is {length:.1f}s — sizzle reel wants 6-8s (4-10 tolerated)")
        if isinstance(dur, (int, float)) and hw.get("end_s", 0) > dur:
            errs.append("highlight_window ends after duration_target_s")

    if prev_t and isinstance(dur, (int, float)) and prev_t > dur:
        errs.append(f"last timeline step t={prev_t} exceeds duration_target_s={dur}")

    # Brand assets this demo's render needs
    for asset in (BRAND_DIR / f"intro-{demo}.png", BRAND_DIR / "outro.png",
                  BRAND_DIR / "asciinema-ghost.json", BRAND_DIR / "frames.json",
                  BRAND_DIR / "frame-pixel8.png"):
        if not asset.exists():
            errs.append(f"missing brand asset {asset.relative_to(REPO_ROOT)}")
    return errs


def timeline_end(spec: dict) -> float:
    """Seconds of content: last step's t plus that step's own duration."""
    last = spec["timeline"][-1]
    tail = (last.get("args") or {}).get("seconds", 0) if last["action"] != "terminal_type" else 8
    return float(last["t"]) + float(tail) + 2.0


# ── Tool checks ───────────────────────────────────────────────────────────────

def check_tools(need_ocr: bool = True) -> list[str]:
    missing = [t for t in ("asciinema", "agg", "ffmpeg", "adb") if not shutil.which(t)]
    if need_ocr and not shutil.which("tesseract"):
        missing.append("tesseract")
    return missing


# ── Phone helpers ─────────────────────────────────────────────────────────────

def get_device(serial: str | None):
    from gitd.bots.common.adb import Device  # lazy: not needed for --dry-run
    out = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout
    attached = [l.split()[0] for l in out.splitlines()[1:] if l.strip().endswith("device")]
    if serial is None:
        serial = os.environ.get("ANDROID_SERIAL")
    if serial is None:
        if len(attached) != 1:
            die(f"pass --serial: {len(attached)} devices attached")
        serial = attached[0]
    if serial not in attached:
        die(f"device {serial} not attached (attached: {attached or 'none'})")
    return Device(serial)


def phone_privacy_prep(dev, workdir: Path, patterns) -> dict:
    """Best-effort device hygiene before recording (#787). Returns a dict of
    settings we changed so they can be restored afterwards. Hard-fails only on
    the OCR gate — everything else degrades to a warning + checklist item."""
    restore: dict[str, str] = {}

    def soft(desc, *args):
        r = dev.adb_soft("shell", *args)
        if r.returncode != 0:
            log(f"  (soft-fail, do manually if needed) {desc}: {r.stderr or r.stdout}")
        return r

    log("phone prep: wake+unlock, DND on, clear notifications, hide status bar, clear recents")
    # Best-effort unlock so we never record a lock screen (works for no-PIN /
    # swipe-only screens; PIN-locked devices must be unlocked by hand — the
    # pre-record OCR screenshot below is taken of whatever is actually shown)
    soft("wake", "input", "keyevent", "KEYCODE_WAKEUP")
    time.sleep(0.4)
    soft("dismiss keyguard", "input", "keyevent", "82")
    soft("swipe up", "input", "swipe", "540", "1800", "540", "700", "200")
    restore["zen_mode"] = dev.adb_soft("shell", "settings", "get", "global", "zen_mode").stdout or "0"
    soft("enable DND", "settings", "put", "global", "zen_mode", "1")
    soft("clear notifications", "service", "call", "notification", "1")
    restore["policy_control"] = dev.adb_soft(
        "shell", "settings", "get", "global", "policy_control").stdout or "null"
    soft("hide status bar", "settings", "put", "global", "policy_control", "immersive.status=*")
    soft("clear recents", "am", "kill-all")
    # Time freeze needs root on production builds — try, warn on failure.
    soft("disable auto time", "settings", "put", "global", "auto_time", "0")

    # Pre-record screenshot → OCR gate: refuse to record a dirty screen.
    shot = workdir / "prep_check.png"
    with shot.open("wb") as f:
        subprocess.run(["adb", "-s", dev.serial, "exec-out", "screencap", "-p"],
                       stdout=f, check=True)
    text = ocr_png(shot)
    hits = scan_text(text, patterns)
    if hits:
        for src, m in hits:
            log(f"  FORBIDDEN on screen before recording: {src!r} matched {m[:3]}…")
        die("phone screen shows forbidden content — clean the device (see "
            "scripts/privacy/RECORDING_CHECKLIST.md) and retry")
    log("phone prep: pre-record OCR gate clean")
    return restore


def phone_privacy_restore(dev, restore: dict) -> None:
    dev.adb_soft("shell", "settings", "put", "global", "zen_mode", restore.get("zen_mode", "0"))
    pc = restore.get("policy_control") or "null"
    dev.adb_soft("shell", "settings", "put", "global", "policy_control", pc)


def run_setup(dev, spec: dict) -> None:
    for s in spec.get("setup") or []:
        step, args = s["step"], s.get("args") or {}
        log(f"setup: {step} {args or ''}")
        if step == "kill_all_apps":
            dev.adb_soft("shell", "am", "kill-all")
        elif step == "wake_unlock":
            dev.adb_soft("shell", "input", "keyevent", "KEYCODE_WAKEUP")
            time.sleep(0.5)
            dev.adb_soft("shell", "input", "keyevent", "82")
        elif step == "launch_app":
            dev.adb("shell", "monkey", "-p", args["package"],
                    "-c", "android.intent.category.LAUNCHER", "1")
            time.sleep(float(args.get("settle_s", 2)))
        elif step == "clear_app":
            dev.adb_soft("shell", "pm", "clear", args["package"])
        elif step == "install_apk":
            dev.adb_show("install", "-r", str(REPO_ROOT / args["path"]))
        elif step == "shell":
            dev.adb_soft("shell", *shlex.split(args["cmd"]))


class PhoneRecorder:
    """adb shell screenrecord in a background thread; finalized via SIGINT so
    the mp4 moov atom is written, then pulled off the device."""

    REMOTE = "/sdcard/ghost_demo_rec.mp4"

    def __init__(self, serial: str, limit_s: float, size: str | None):
        self.serial = serial
        self.limit_s = min(int(limit_s), 179)  # screenrecord hard-caps at 180s
        self.size = size
        self.proc: subprocess.Popen | None = None
        self.started_at = 0.0

    def start(self) -> None:
        cmd = ["adb", "-s", self.serial, "shell", "screenrecord",
               "--bit-rate", "8000000", "--time-limit", str(self.limit_s)]
        if self.size:
            cmd += ["--size", self.size]
        cmd.append(self.REMOTE)
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.started_at = time.monotonic()
        time.sleep(1.5)  # screenrecord startup latency before frames roll

    def stop_and_pull(self, dest: Path) -> None:
        subprocess.run(["adb", "-s", self.serial, "shell", "pkill", "-2", "screenrecord"],
                       capture_output=True)
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        time.sleep(1.0)  # let the device flush the file
        run(["adb", "-s", self.serial, "pull", self.REMOTE, str(dest)], "adb pull recording")
        subprocess.run(["adb", "-s", self.serial, "shell", "rm", "-f", self.REMOTE],
                       capture_output=True)


# ── Inner mode: executes the timeline inside the asciinema pty ────────────────

def type_and_run(cmd: str, env: dict, exec_cmd: str | None = None) -> None:
    prompt = "\x1b[1;32mghost@demo\x1b[0m \x1b[1;34m~\x1b[0m $ "
    sys.stdout.write(prompt)
    sys.stdout.flush()
    for ch in cmd:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(TYPE_DELAY_S)
    sys.stdout.write("\n")
    sys.stdout.flush()
    subprocess.run(exec_cmd or cmd, shell=True, env=env, cwd=str(REPO_ROOT))


def run_inner(plan_path: Path) -> int:
    """Runs INSIDE `asciinema rec -c ...`: replays the timeline in real time.
    Terminal actions render into the recording; phone actions drive the device
    silently so both recordings stay in sync."""
    plan = json.loads(Path(plan_path).read_text())
    spec, serial = plan["spec"], plan.get("serial")
    dev = None
    if serial:
        from gitd.bots.common.adb import Device
        dev = Device(serial)
    env = scrubbed_env(dict(os.environ))
    env["PYTHONPATH"] = str(REPO_ROOT)
    if serial:
        env["ANDROID_SERIAL"] = serial
    # iOS support is feature-gated (default off since PR #33); demos that
    # exercise it need the opt-in flag inside the recorded shell.
    if spec.get("device") in ("ios", "both"):
        env["GITD_ENABLE_IOS"] = "1"
    # spec-declared extras (validated: no secret-shaped names/values)
    env.update({k: str(v) for k, v in (spec.get("env") or {}).items()})

    t0 = time.monotonic()
    for step in spec["timeline"]:
        target = float(step["t"])
        lag = target - (time.monotonic() - t0)
        if lag > 0:
            time.sleep(lag)
        action, args = step["action"], step.get("args") or {}
        if action == "terminal_type":
            # exec_cmd: run this instead of the displayed cmd (e.g. hide a
            # demo-only pacing pipe from the typed one-liner)
            type_and_run(args["cmd"], env, exec_cmd=args.get("exec_cmd"))
        elif action == "terminal_exec":
            # run without typing the command — the command draws its own
            # terminal visuals (e.g. the Claude Code TUI driver)
            subprocess.run(args["cmd"], shell=True, env=env, cwd=str(REPO_ROOT))
        elif action in ("wait_for_phone", "phone_screenshot_pause", "sleep"):
            time.sleep(float(args["seconds"]))
        elif action == "phone_tap":
            dev.tap(args["x"], args["y"], delay=float(args.get("delay", 0.6)))
        elif action == "phone_swipe":
            dev.swipe(args["x1"], args["y1"], args["x2"], args["y2"],
                      ms=int(args.get("ms", 500)))
        elif action == "phone_key":
            dev.adb("shell", "input", "keyevent", str(args["key"]))
    time.sleep(2.0)  # trailing air so the last output breathes
    Path(plan["done_marker"]).write_text("ok")
    return 0


# ── Post-processing ───────────────────────────────────────────────────────────

def ocr_png(png: Path) -> str:
    r = subprocess.run(["tesseract", str(png), "stdout"], capture_output=True, text=True)
    return r.stdout or ""


def render_terminal(cast: Path, out_mp4: Path, workdir: Path) -> None:
    theme = json.loads((BRAND_DIR / "asciinema-ghost.json").read_text())
    gif = workdir / "terminal.gif"
    # agg >= 1.9 renders Noto Color Emoji (CBDT bitmap) in color; 1.4.x leaves
    # emoji as blank gaps regardless of renderer/font flags
    agg_bin = shutil.which("agg-1.9") or "agg"
    # the font stack lacks U+276F (Claude Code's ❯ input prompt) and renders
    # it as mojibake — substitute a plain '>' before rendering (visual only)
    glyphfix = workdir / (cast.stem + "_glyphfix.cast")
    txt = cast.read_text()
    # casts may store specials as literal UTF-8 OR as \uXXXX JSON escapes —
    # substitute BOTH forms (missing either resurfaces the mojibake)
    for lit, esc, repl in ((chr(0x276F), r"\\u276[fF]", ">"),
                           (chr(0x00A0), r"\\u00[aA]0", " ")):
        txt = txt.replace(lit, repl)
        txt = re.sub(esc, repl, txt)
    txt = re.sub(r"[\u2800-\u28ff]", "·", txt)
    txt = re.sub(r"\\u28[0-9a-fA-F]{2}", "·", txt)
    glyphfix.write_text(txt)
    cast = glyphfix
    run([agg_bin,
         "--theme", theme["agg"]["theme_arg"],
         "--font-dir", str(BRAND_DIR / "fonts"),
         "--font-dir", "/usr/share/fonts/truetype/noto",
         "--font-family",
         theme.get("font_family", "JetBrains Mono") + ",Noto Color Emoji",
         "--font-size", str(theme.get("font_size", 16)),
         "--line-height", str(theme.get("line_height", 1.4)),
         "--fps-cap", str(FPS),
         # never compress idle time — the terminal must stay in real time
         # or it desyncs from the phone recording
         "--idle-time-limit", "600",
         str(cast), str(gif)], "agg render", heavy=True)
    run(["ffmpeg", "-y", "-i", str(gif),
         "-vf", f"fps={FPS},scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
         "-c:v", "libx264", "-crf", "18",
         str(out_mp4)], "gif→mp4", heavy=True)


def ass_time(s: float) -> str:
    cs = int(round(s * 100))
    return f"{cs//360000}:{cs//6000%60:02d}:{cs//100%60:02d}.{cs%100:02d}"


def build_captions(spec: dict, path: Path) -> None:
    """ASS subtitles from timeline captions, bottom-center, Ghost palette."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {CANVAS_W}
PlayResY: {CANVAS_H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Ghost,Outfit,54,&H00E9EDE8,&H00FFFFFF,&H00000000,&H00000000,700,0,0,0,100,100,0,0,1,0,0,7,42,40,88,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    captioned = [s for s in spec["timeline"] if s.get("caption")]
    end_all = timeline_end(spec)
    lines = []
    for i, s in enumerate(captioned):
        start = float(s["t"])
        end = float(captioned[i + 1]["t"]) if i + 1 < len(captioned) else min(start + 5, end_all)
        end = min(end, start + 6)
        text = s["caption"].replace("\n", " ").strip()
        # C-prime-4 editorial headline: two-tone — last sentence in Ghost
        # green (ASS colors are BGR: &HA0E500& == #00e5a0). Long copy drops
        # to 44px so it clears the window top (y=208).
        parts = text.rstrip(".").split(". ")
        if len(parts) > 1:
            head, tail = ". ".join(parts[:-1]) + ". ", parts[-1] + "."
        else:
            head, tail = text, ""
        size_tag = r"{\fs44}" if len(text) > 44 else ""
        two_tone = head + (r"{\c&HA0E500&}" + tail if tail else "")
        lines.append(
            f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Ghost,,0,0,0,,"
            r"{\fad(200,200)}" + size_tag + two_tone)
    path.write_text(header + "\n".join(lines) + "\n")


def composite(spec: dict, workdir: Path, term_mp4: Path, phone_mp4: Path,
              phone_offset_s: float, out_webm: Path) -> None:
    """One-shot filter graph: intro card + [terminal | framed phone + captions]
    + outro card → 720p VP9 WebM."""
    demo = spec["demo"]
    frames = json.loads((BRAND_DIR / "frames.json").read_text())
    device_frame = "iphone15pro" if spec.get("device") == "ios" else "pixel8"
    fr = frames[device_frame]
    frame_png = BRAND_DIR / f"frame-{device_frame}.png"
    rx, ry, rw, rh = fr["screen_rect"]
    rx += FRAME_X_OFFSET
    content_s = timeline_end(spec)
    captions = workdir / "captions.ass"
    build_captions(spec, captions)

    intro = BRAND_DIR / f"intro-{demo}.png"
    # Motion layouts open with an animated intro (design-review's mp4 whose
    # final frame is pixel-matched to the code pane at the seam) instead of the
    # 1s static card. Input [0] becomes a real video decode of its natural
    # length; the concat is unchanged.
    intro_motion = BRAND_DIR / f"intro-{demo}-motion.mp4"
    use_motion_intro = spec.get("layout") == "three_window" and intro_motion.exists()
    outro = BRAND_DIR / "outro.png"
    bgpng = BRAND_DIR / "cprime-bg.png"       # glow + kicker baked
    mascot_l = BRAND_DIR / "cprime-mascot.png"  # peeks from BEHIND the window
    # 3-pane motion layout: a short terminal window (term_rows) + a code pane
    # overlay below it. Keyed on spec.code_pane; falls back to the standard
    # single-window chrome. The code pane is a full-canvas RGBA asset owned by
    # design-review (pixel-identical to the animated intro's final frame so the
    # seam diff passes) — consumed verbatim, never redrawn here.
    # 3-pane motion layout (spec: layout: three_window). The code pane is a
    # pre-rendered RGBA asset owned by design-review (codepane-<demo>-v3.png),
    # NOT live-rendered from code_pane_source — that key names the truth the
    # asset must mirror, for the record + reviewers, not a render input.
    three_pane = spec.get("layout") == "three_window"
    code_pane = spec.get("code_pane_asset",
                         f"codepane-{demo}-v3.png") if three_pane else None
    chrome = BRAND_DIR / (
        "terminal-frame-macos-small.png" if code_pane else "terminal-frame-macos.png")

    fc = (
        # content background (static png with glow + kicker) + panels
        f"color=c=0x{BG_HEX}:s={CANVAS_W}x{CANVAS_H}:d={content_s}:r={FPS}[bgc];"
        f"[5:v]format=rgba[bgp];"
        f"[bgc][bgp]overlay=0:0[bg];"
        # mascot UNDER the chrome (The Haunt), chrome UNDER the terminal
        f"[7:v]format=rgba[mascot];"
        f"[bg][mascot]overlay=0:0[m0];"
        f"[6:v]format=rgba[chrome];"
        f"[m0][chrome]overlay=0:0[c0];"
        f"[2:v]null[term];"  # native render — zero rescale
        f"[c0][term]overlay={TERM_X}:{TERM_Y}[c1];"
        f"[3:v]trim=start={max(phone_offset_s, 0)},setpts=PTS-STARTPTS,"
        f"scale={rw}:{rh},setsar=1[phone];"
        f"[c1][phone]overlay={rx}:{ry}[c2];"
        f"[4:v]format=rgba[framepng];"
        f"[c2][framepng]overlay={FRAME_X_OFFSET}:0:format=auto[c3];"
        # code pane (3-pane only): full-canvas overlay above the phone/frame
        + (f"[8:v]format=rgba[codepane];"
           f"[c3][codepane]overlay=0:0[c4];" if code_pane else
           f"[c3]null[c4];")
        + f"[c4]subtitles='{captions}':fontsdir='{BRAND_DIR / 'fonts'}',"
        f"trim=duration={content_s},"
        f"setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[content];"
        # cards
        f"[0:v]scale={CANVAS_W}:{CANVAS_H},fps={FPS},format=yuv420p[intro];"
        f"[1:v]scale={CANVAS_W}:{CANVAS_H},fps={FPS},format=yuv420p[outro];"
        f"[intro][content][outro]concat=n=3:v=1:a=0,"
        f"scale=1280:720[out]"
    )
    inputs = [
        *(["-i", str(intro_motion)] if use_motion_intro
          else ["-loop", "1", "-t", str(INTRO_S), "-i", str(intro)]),
        "-loop", "1", "-t", str(OUTRO_S), "-i", str(outro),
        "-i", str(term_mp4),
        "-i", str(phone_mp4),
        "-i", str(frame_png),
        "-i", str(bgpng),
        "-i", str(chrome),
        "-i", str(mascot_l),
    ]
    if code_pane:
        inputs += ["-i", str(BRAND_DIR / code_pane)]  # input [8]
    run(["ffmpeg", "-y", *inputs,
         "-filter_complex", fc, "-map", "[out]",
         "-c:v", "libvpx-vp9", "-crf", "41", "-b:v", "0",
         "-deadline", "good", "-cpu-used", "2", "-row-mt", "1", "-an",
         str(out_webm)], "composite render", heavy=True)


def ocr_gate(webm: Path, workdir: Path, patterns) -> list[str]:
    """Extract up to 30 frames at 2s intervals, OCR each, scan against the
    forbidden lists. Returns list of human-readable violations (empty = pass)."""
    frames_dir = workdir / "ocr_frames"
    frames_dir.mkdir(exist_ok=True)
    run(["ffmpeg", "-y", "-i", str(webm), "-vf", "fps=1/2", "-frames:v", "30",
         str(frames_dir / "f%03d.png")], "OCR frame extraction", heavy=True)
    frames = sorted(frames_dir.glob("f*.png"))
    if not frames:
        # fail closed: a gate that scanned nothing must never read as "clean"
        # (corrupt-but-exit-0 webm, sub-2s video, bad -vf all land here)
        die(f"OCR gate extracted 0 frames from {webm} — refusing to pass an "
            f"unscanned video")
    violations = []
    for png in frames:
        text = ocr_png(png)
        (png.with_suffix(".txt")).write_text(text)
        for src, m in scan_text(text, patterns):
            ts = (int(png.stem[1:]) - 1) * 2
            violations.append(f"{png.name} (~t={ts}s): pattern {src!r} matched {m[:3]}…")
    return violations


def write_snippet(spec: dict, path: Path) -> None:
    cmds = [s["args"]["cmd"] for s in spec["timeline"] if s["action"] == "terminal_type"]
    body = "\n".join(cmds)
    path.write_text(
        f"# {spec['title']} — commands from this demo\n"
        f"# {spec['outro']['cta_link']}\n\n{body}\n")


# ── Modes ─────────────────────────────────────────────────────────────────────

def do_list() -> int:
    copy = load_copy()
    for demo_id in sorted(copy, key=lambda d: copy[d].get("sizzle_order") or 99):
        has_spec = (SHOWCASE_DIR / demo_id / "spec.yaml").exists()
        has_webm = (SHOWCASE_DIR / demo_id / "demo.webm").exists()
        flags = ("spec " if has_spec else "     ") + ("webm" if has_webm else "")
        print(f"  {demo_id:24s} {flags}")
    return 0


def do_dry_run(demo: str) -> int:
    spec = load_spec(demo)
    errs = validate_spec(spec)
    missing = check_tools(need_ocr=False)
    if missing:
        log(f"note: tools missing on this host (fine for dry-run): {', '.join(missing)}")
    if errs:
        for e in errs:
            print(f"  ✗ {e}")
        die(f"spec for '{demo}' has {len(errs)} problem(s)")
    n_term = sum(1 for s in spec["timeline"] if s["action"] == "terminal_type")
    n_phone = sum(1 for s in spec["timeline"] if s["action"].startswith("phone"))
    log(f"✓ '{demo}' valid — {len(spec['timeline'])} steps "
        f"({n_term} terminal, {n_phone} phone), ~{timeline_end(spec):.0f}s content, "
        f"highlight {spec['highlight_window']['start_s']}–{spec['highlight_window']['end_s']}s")
    return 0


def do_record(demo: str, serial: str | None, skip_phone_prep: bool,
              keep_workdir: bool, no_local_patterns: bool = False) -> int:
    spec = load_spec(demo)
    errs = validate_spec(spec)
    if errs:
        for e in errs:
            print(f"  ✗ {e}")
        die("spec invalid — fix before recording (or run --dry-run)")
    missing = check_tools()
    if missing:
        die(f"missing tools: {', '.join(missing)} — the privacy gate requires all of them")
    if spec["device"] == "ios":
        die("ios recording is manual for now: point QuickTime (New Movie Recording) "
            "at the iPhone, then composite by hand. Android automation only.")

    patterns = load_forbidden()
    if not (Path(__file__).parent / "privacy" / "FORBIDDEN.local.txt").exists():
        if no_local_patterns:
            log("WARNING: running without FORBIDDEN.local.txt (--no-local-patterns) — "
                "personal identifiers are NOT enforced. Never ship this recording.")
        else:
            die("scripts/privacy/FORBIDDEN.local.txt missing — the personal identifier "
                "list is not set up (see RECORDING_CHECKLIST.md §3). If you really "
                "want to record without it, pass --no-local-patterns.")

    workdir = REPO_ROOT / ".recordings" / demo
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    log(f"workdir {workdir}")
    if spec.get("platform_notes"):
        log(f"platform notes: {spec['platform_notes']}")

    dev = get_device(serial)
    restore = {}
    rec = None
    try:
        if skip_phone_prep:
            log("phone prep SKIPPED (--skip-phone-prep) — dev runs only, never ship this")
        else:
            restore = phone_privacy_prep(dev, workdir, patterns)
        run_setup(dev, spec)

        content_s = timeline_end(spec)
        rec = PhoneRecorder(dev.serial, content_s + 10, spec.get("record_size"))
        log(f"recording ~{content_s:.0f}s of content on {dev.serial}")
        rec.start()

        plan = {"spec": spec, "serial": dev.serial,
                "done_marker": str(workdir / "inner_done")}
        plan_path = workdir / "plan.json"
        plan_path.write_text(json.dumps(plan))

        cast = workdir / "terminal.cast"
        phone_offset = time.monotonic() - rec.started_at
        # per-demo terminal height (motion 3-pane demos record a short window,
        # e.g. LINES=14); defaults to the global TERM_ROWS
        term_rows = int(spec.get(
            "term_rows", 14 if spec.get("layout") == "three_window" else TERM_ROWS))
        env = dict(os.environ)
        env.update({"COLUMNS": str(TERM_COLS), "LINES": str(term_rows),
                    "PYTHONUNBUFFERED": "1"})
        inner_cmd = f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(__file__).resolve()))} --_inner {shlex.quote(str(plan_path))}"
        r = subprocess.run(
            ["asciinema", "rec", "--overwrite", "--cols", str(TERM_COLS),
             "--rows", str(term_rows), "-c", inner_cmd, str(cast)],
            env=env)
        if r.returncode != 0 or not (workdir / "inner_done").exists():
            die("timeline execution failed (see output above)")

        phone_mp4 = workdir / "phone.mp4"
        rec.stop_and_pull(phone_mp4)
        rec = None
    finally:
        if rec and rec.proc:
            rec.proc.kill()
        if restore:
            phone_privacy_restore(dev, restore)

    # ── post-process ──
    host = socket.gethostname()
    user = os.environ.get("USER", "")
    extra = [(dev.serial, "<ANDROID_DEVICE>")]
    # Every OTHER attached serial can leak too (e.g. `gitd doctor` lists them)
    out = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout
    others = [l.split()[0] for l in out.splitlines()[1:]
              if l.strip().endswith("device") and l.split()[0] != dev.serial]
    extra += [(s, f"<ANDROID_DEVICE_{i+2}>") for i, s in enumerate(others)]
    if host:
        extra.append((host, "ghost-dev-linux"))
    if user and user != "ghost":
        extra.append((f"/home/{user}", "~"))
        extra.append((f"{user}@", "ghost@"))

    cast_scrubbed = workdir / "terminal_scrubbed.cast"
    scrub_cast(workdir / "terminal.cast", cast_scrubbed, extra=extra,
               cols=TERM_COLS, rows=int(spec.get(
                   "term_rows", 14 if spec.get("layout") == "three_window" else TERM_ROWS)))
    hits = scan_text(cast_scrubbed.read_text(), patterns)
    if hits:
        for src, m in hits:
            log(f"  FORBIDDEN in scrubbed terminal cast: {src!r} matched {m[:3]}…")
        die("terminal recording still contains forbidden content after scrubbing — "
            "extend scrub.py substitutions or fix the demo commands")

    log("rendering terminal (agg)")
    term_mp4 = workdir / "terminal.mp4"
    render_terminal(cast_scrubbed, term_mp4, workdir)

    log("compositing final video (ffmpeg)")
    out_webm = workdir / "demo.webm"
    composite(spec, workdir, term_mp4, workdir / "phone.mp4",
              phone_offset_s=phone_offset, out_webm=out_webm)

    log("privacy OCR gate: extracting frames + tesseract scan")
    violations = ocr_gate(out_webm, workdir, patterns)
    if violations:
        for v in violations:
            log(f"  FORBIDDEN {v}")
        die(f"OCR gate FAILED ({len(violations)} hit(s)) — output stays quarantined in "
            f"{workdir}, nothing was copied to site/public/. Inspect the frames, fix "
            f"the leak, re-record.")
    log("privacy OCR gate: clean")

    out_dir = SHOWCASE_DIR / demo
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out_webm, out_dir / "demo.webm")
    hw = spec.get("highlight_window") or {}
    # Skip past the intro before grabbing the poster. Motion layouts open with
    # an animated intro whose real length (≈7.8s) replaces the 1s static card.
    intro_motion = BRAND_DIR / f"intro-{demo}-motion.mp4"
    intro_dur = INTRO_S
    if spec.get("layout") == "three_window" and intro_motion.exists():
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(intro_motion)],
            capture_output=True, text=True)
        intro_dur = float(probe.stdout.strip() or INTRO_S)
    poster_ss = intro_dur + float(hw.get("start_s", 2)) + 1.0
    run(["ffmpeg", "-y", "-ss", str(poster_ss), "-i", str(out_dir / "demo.webm"),
         "-frames:v", "1", str(out_dir / "poster.png")], "poster extraction")
    write_snippet(spec, out_dir / "snippet.py")

    size_mb = (out_dir / "demo.webm").stat().st_size / 1e6
    log(f"DONE → {out_dir / 'demo.webm'} ({size_mb:.1f} MB), poster.png, snippet.py")
    if not keep_workdir:
        shutil.rmtree(workdir)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Ghost showcase demo recorder")
    ap.add_argument("--demo", help="demo id (must exist in copy.yaml + have spec.yaml)")
    ap.add_argument("--serial", help="android device serial (else ANDROID_SERIAL / sole device)")
    ap.add_argument("--dry-run", action="store_true", help="validate spec + assets, don't record")
    ap.add_argument("--list", action="store_true", help="list demos and their asset status")
    ap.add_argument("--skip-phone-prep", action="store_true",
                    help="DEV ONLY: skip DND/notification/OCR pre-checks")
    ap.add_argument("--keep-workdir", action="store_true", help="keep .recordings/<demo> for debugging")
    ap.add_argument("--no-local-patterns", action="store_true",
                    help="DEV ONLY: allow recording without FORBIDDEN.local.txt "
                         "(personal identifiers unenforced — never ship the result)")
    ap.add_argument("--_inner", metavar="PLAN", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args._inner:
        return run_inner(Path(args._inner))
    if args.list:
        return do_list()
    if not args.demo:
        ap.error("--demo is required (or --list)")
    if args.dry_run:
        return do_dry_run(args.demo)
    return do_record(args.demo, args.serial, args.skip_phone_prep, args.keep_workdir,
                     args.no_local_patterns)


if __name__ == "__main__":
    sys.exit(main())
