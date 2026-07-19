"""Unit tests for the chat-trace → recorded-step distiller (M1).

Pure/device-free: builds a synthetic message trace (dicts shaped like the
ChatMessage stream that agent_chat.py records) and asserts the distilled
recorded-skill steps.
"""

from gitd.skills.trace_to_steps import actuating_tools, distill_steps


def _call(tool_name, tool_args, tool_id=""):
    return {"role": "tool_call", "tool_name": tool_name, "tool_args": tool_args, "tool_id": tool_id, "content": ""}


def _result(content, tool_id=""):
    return {"role": "tool_result", "tool_name": "", "tool_args": {}, "tool_id": tool_id, "content": content}


def _assistant(text):
    return {"role": "assistant", "tool_name": "", "tool_args": {}, "tool_id": "", "content": text}


def test_core_vocab_mapping():
    trace = [
        _assistant("Let's open Reddit."),
        _call("launch_app", {"device": "d", "package": "com.reddit.frontpage"}),
        _result("Launched com.reddit.frontpage"),
        _call("tap", {"device": "d", "x": 540, "y": 800}),
        _result("Tapped (540, 800)"),
        _call("type_text", {"device": "d", "text": "localllama"}),
        _result("Typed"),
        _call("type_unicode", {"device": "d", "text": "café"}),
        _result("Typed unicode"),
        _call("press_key", {"device": "d", "key": "ENTER"}),
        _result("Pressed"),
        _call("swipe", {"device": "d", "x1": 540, "y1": 1400, "x2": 540, "y2": 600, "duration_ms": 500}),
        _result("Swiped"),
        _call("press_back", {"device": "d"}),
        _result("Back"),
        _call("press_home", {"device": "d"}),
        _result("Home"),
        _call("wait", {"seconds": 3}),
        _result("Waited"),
    ]
    steps = distill_steps(trace)
    actions = [(s["action"], {k: v for k, v in s.items() if k not in ("action", "description")}) for s in steps]
    assert actions == [
        ("launch", {"package": "com.reddit.frontpage"}),
        ("tap", {"x": 540, "y": 800}),
        ("type", {"text": "localllama"}),
        ("type", {"text": "café"}),  # type_unicode also maps to 'type'
        ("key", {"key": "ENTER"}),
        ("swipe", {"x1": 540, "y1": 1400, "x2": 540, "y2": 600}),  # duration dropped
        ("back", {}),
        ("home", {}),
        ("wait", {"seconds": 3}),
    ]


def test_tap_element_recovers_coords_and_label():
    trace = [
        _call("get_elements", {"device": "d"}, tool_id="t0"),
        _result('[{"idx":3,"text":"Search"}]', tool_id="t0"),
        _call("tap_element", {"device": "d", "idx": 3}, tool_id="t1"),
        _result("Tapped element #3 'Search' at (712, 145)", tool_id="t1"),
    ]
    steps = distill_steps(trace)
    # get_elements dropped; tap_element → coordinate tap recovered from result
    assert len(steps) == 1
    assert steps[0]["action"] == "tap"
    assert steps[0]["x"] == 712 and steps[0]["y"] == 145
    assert steps[0]["description"] == "Search"  # label from the result string


def test_noise_and_unknown_tools_dropped():
    trace = [
        _call("screenshot", {"device": "d"}),
        _result("<image>"),
        _call("get_screen_tree", {"device": "d"}),
        _result("(tree)"),
        _call("ocr_screen", {"device": "d"}),
        _result("text"),
        _call("find_on_screen", {"device": "d", "query": "x"}),
        _result("found"),
        _call("classify_screen", {"device": "d"}),
        _result("home"),
        _call("create_skill", {"device": "d", "name": "z"}),  # meta / not actuating
        _result("ok"),
        _call("sub_agent", {"device": "d", "goal": "y"}),  # growing vocab, not in allow-list
        _result("done"),
        _call("tap", {"device": "d", "x": 1, "y": 2}),
        _result("Tapped (1, 2)"),
    ]
    steps = distill_steps(trace)
    assert len(steps) == 1 and steps[0]["action"] == "tap"


def test_tap_without_coords_is_dropped():
    trace = [
        _call("tap", {"device": "d"}),  # no x/y → unusable
        _result("err"),
    ]
    assert distill_steps(trace) == []


def test_long_press_open_url_launch_intent():
    trace = [
        _call("long_press", {"device": "d", "x": 100, "y": 200, "duration_ms": 1200}),
        _result("Long pressed"),
        _call("open_url", {"device": "d", "url": "https://www.reddit.com/r/LocalLLaMA/"}),
        _result("Opened"),
        _call("launch_intent", {"device": "d", "action": "android.intent.action.VIEW", "data": "geo:0,0"}),
        _result("Intent sent"),
    ]
    steps = distill_steps(trace)
    assert steps[0] == {
        "action": "long_press",
        "x": 100,
        "y": 200,
        "duration_ms": 1200,
        "description": steps[0].get("description", ""),
    } or (steps[0]["action"] == "long_press" and steps[0]["x"] == 100 and steps[0]["duration_ms"] == 1200)
    assert steps[1]["action"] == "open_url" and steps[1]["url"].endswith("/r/LocalLLaMA/")
    assert steps[2]["action"] == "launch_intent"
    assert steps[2]["intent_action"] == "android.intent.action.VIEW"  # renamed to avoid dispatch-key collision
    assert steps[2]["data"] == "geo:0,0"


def test_description_from_preceding_assistant_text():
    trace = [
        _assistant("Now I'll tap the search box to enter the query."),
        _call("tap", {"device": "d", "x": 5, "y": 6}),
        _result("Tapped (5, 6)"),
    ]
    steps = distill_steps(trace)
    assert steps[0]["description"].startswith("Now I'll tap the search box")


def test_positional_result_fallback_without_tool_id():
    # ollama/openrouter may not carry tool_id → pair with next positional result
    trace = [
        _call("tap_element", {"device": "d", "idx": 0}),  # no tool_id
        _result("Tapped element #0 'Home' at (50, 60)"),  # no tool_id
    ]
    steps = distill_steps(trace)
    assert steps[0]["action"] == "tap" and steps[0]["x"] == 50 and steps[0]["y"] == 60


def test_allow_list_is_the_actuating_set():
    expected = {
        "tap", "tap_element", "swipe", "type_text", "type_unicode", "press_key",
        "press_back", "press_home", "long_press", "launch_app", "launch_intent",
        "open_url", "wait",
    }
    assert actuating_tools() == expected
