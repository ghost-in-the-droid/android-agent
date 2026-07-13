"""Device-shell command-injection guards for the adb `input` boundary.

`adb shell <argv>` re-parses its arguments through the *device* shell, so any
agent/attacker-controlled value sent to `input keyevent` / `input text` (e.g. a
prompt-injected web page the agent transcribes) could otherwise break out and run
arbitrary device commands (reboot, pm uninstall, settings, wipe). These verify
the two shared guards neutralize that.
"""

import shlex

import pytest

from gitd.bots.common.adb import ascii_typeable, input_text_arg, normalize_keycode


# ── normalize_keycode (press_key vector) ─────────────────────────────────────

def test_normalize_keycode_adds_prefix_and_accepts_valid():
    assert normalize_keycode("HOME") == "KEYCODE_HOME"
    assert normalize_keycode("KEYCODE_BACK") == "KEYCODE_BACK"
    assert normalize_keycode("KEYCODE_DPAD_DOWN") == "KEYCODE_DPAD_DOWN"
    assert normalize_keycode("VOLUME_UP") == "KEYCODE_VOLUME_UP"


@pytest.mark.parametrize(
    "payload",
    [
        "KEYCODE_HOME; reboot",
        "HOME; reboot",
        "KEYCODE_HOME && pm uninstall com.foo",
        "KEYCODE_HOME | sh",
        "KEYCODE_HOME $(reboot)",
        "KEYCODE_HOME `reboot`",
        "KEYCODE_HOME\nreboot",
        "KEYCODE_HOME ; wipe",
        "home",           # lowercase — not a real keycode
        "KEYCODE_",        # empty body
        "",
    ],
)
def test_normalize_keycode_rejects_injection_and_junk(payload):
    with pytest.raises(ValueError):
        normalize_keycode(payload)


# ── input_text_arg (type_text vector) ────────────────────────────────────────

def _device_argv(text: str) -> list[str]:
    """What the *device* shell parses from `input text <arg>` — the whole command
    line is re-split by sh on the device, so this mirrors the real boundary."""
    return shlex.split("input text " + input_text_arg(ascii_typeable(text)))


@pytest.mark.parametrize(
    "payload",
    [
        "; reboot",
        "＃reboot",                     # fullwidth — folds toward ascii
        "；reboot",                     # fullwidth semicolon → ascii ';'
        "rm -rf /; reboot",
        "a && pm clear com.foo",
        "x | sh",
        "$(reboot)",
        "`reboot`",
        "a > /sdcard/x",
        "a\nreboot",
        "it's a \"test\"",             # embedded quotes
    ],
)
def test_input_text_never_breaks_out_of_the_device_shell(payload):
    # The device shell must see exactly `input`, `text`, and ONE more token —
    # never a second command. (3 tokens total; the payload is the single arg.)
    argv = _device_argv(payload)
    assert argv[:2] == ["input", "text"]
    assert len(argv) == 3, f"payload broke into extra device-shell tokens: {argv}"


def test_input_text_preserves_normal_text():
    # plain ascii with spaces: %s-encoded, no quoting needed, types verbatim
    assert input_text_arg("hello world") == "hello%sworld"
    # the fullwidth-semicolon attack folds to a literal ';' that types as text
    assert shlex.split("input text " + input_text_arg(ascii_typeable("；reboot")))[2] == ";reboot"
