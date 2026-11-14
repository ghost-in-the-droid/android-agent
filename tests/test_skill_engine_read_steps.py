"""YAML read primitives: read_text, tap_nth, compare, for_each, long_press by locator."""
import pytest

from gitd.skills.engine.context import RunContext
from gitd.skills.engine.dispatch import _all_nodes, dispatch
from gitd.skills.engine.errors import ParamError, StepFailedError
from gitd.skills.engine.interpolate import interpolate

XML = (
    '<hierarchy>'
    '<node text="1,234.5" resource-id="app:id/result" bounds="[0,0][100,50]" />'
    '<node text="2+2" resource-id="app:id/item_formula" bounds="[0,60][100,80]" />'
    '<node text="4" resource-id="app:id/item_result" bounds="[0,60][100,80]" />'
    '<node text="3*3" resource-id="app:id/item_formula" bounds="[0,90][100,110]" />'
    '<node text="9" resource-id="app:id/item_result" bounds="[0,90][100,110]" />'
    '<node text="hidden" resource-id="app:id/item_formula" bounds="[0,0][0,0]" />'
    '<node text="OK" content-desc="Confirm" bounds="[10,200][110,240]" checked="true" />'
    '<node text="OK" content-desc="Second" bounds="[10,300][110,340]" />'
    '<node resource-id="app:id/btn_plus" bounds="[0,400][50,450]" />'
    '<node resource-id="app:id/btn_1" bounds="[60,400][110,450]" />'
    '<node resource-id="app:id/btn_equals" bounds="[120,400][170,450]" />'
    '</hierarchy>'
)


class Dev:
    serial = "stub"
    is_fake = True

    def __init__(self, xml=XML):
        self.xml, self.taps, self.adb_calls = xml, [], []

    def dump_xml(self):
        return self.xml

    def tap(self, x, y, delay=0.0):
        self.taps.append((x, y))

    def adb(self, *args):
        self.adb_calls.append(args)


def ctx(**params):
    return RunContext(action_name="a", params=params)


def test_all_nodes_skips_off_screen_and_keeps_document_order():
    nodes = _all_nodes(XML, "id", "app:id/item_formula")
    assert [n["text"] for n in nodes] == ["2+2", "3*3"]
    assert _all_nodes(XML, "desc", "Confirm")[0]["checked"] is True
    assert _all_nodes(XML, "xpath", "x") == []


def test_read_text_stores_in_context_and_result():
    c = ctx()
    dispatch({"action": "read_text", "id": "app:id/result", "store_as": "display"}, c, Dev())
    assert c.extras["display"] == "1,234.5" and c.result["display"] == "1,234.5"
    dispatch({"action": "read_text", "id": "app:id/result", "store_as": "value", "parse": "number"}, c, Dev())
    assert c.result["value"] == 1234.5
    dispatch({"action": "read_text", "id": "app:id/item_formula", "store_as": "formulas", "all": True}, c, Dev())
    assert c.result["formulas"] == ["2+2", "3*3"]
    dispatch({"action": "read_text", "id": "app:id/item_result", "store_as": "results", "all": True, "parse": "number"}, c, Dev())
    assert c.result["results"] == [4.0, 9.0]
    dispatch({"action": "read_text", "text": "OK", "index": 1, "attr": "desc", "store_as": "second"}, c, Dev())
    assert c.result["second"] == "Second"
    dispatch({"action": "read_text", "text": "OK", "index": -1, "attr": "checked", "store_as": "last_checked"}, c, Dev())
    assert c.result["last_checked"] is False
    assert interpolate("display={context.display}", c) == "display=1,234.5"


def test_read_text_failures_and_optional():
    c = ctx()
    with pytest.raises(StepFailedError, match="0 on-screen"):
        dispatch({"action": "read_text", "id": "app:id/missing", "store_as": "x"}, c, Dev())
    dispatch({"action": "read_text", "id": "app:id/missing", "store_as": "x", "required": False}, c, Dev())
    assert c.result["x"] is None
    with pytest.raises(StepFailedError, match="not a number"):
        dispatch({"action": "read_text", "text": "OK", "store_as": "n", "parse": "number"}, c, Dev())
    with pytest.raises(StepFailedError, match="index 5"):
        dispatch({"action": "read_text", "text": "OK", "index": 5, "store_as": "n"}, c, Dev())
    with pytest.raises(ParamError, match="store_as"):
        dispatch({"action": "read_text", "text": "OK"}, c, Dev())
    with pytest.raises(ParamError, match="attr"):
        dispatch({"action": "read_text", "text": "OK", "store_as": "n", "attr": "bounds"}, c, Dev())
    with pytest.raises(ParamError, match="one of id, desc, text"):
        dispatch({"action": "read_text", "store_as": "n"}, c, Dev())


def test_tap_nth_and_long_press_by_locator():
    dev = Dev()
    dispatch({"action": "tap_nth", "text": "OK", "index": 1}, ctx(), dev)
    assert dev.taps == [(60, 320)]
    dispatch({"action": "tap_nth", "text": "OK", "index": -2}, ctx(), dev)
    assert dev.taps[-1] == (60, 220)
    with pytest.raises(StepFailedError):
        dispatch({"action": "tap_nth", "text": "OK", "index": 2}, ctx(), dev)
    dispatch({"action": "long_press", "id": "app:id/btn_plus", "duration_ms": 700}, ctx(), dev)
    assert dev.adb_calls[-1] == ("shell", "input", "swipe", "25", "425", "25", "425", "700")
    dispatch({"action": "long_press", "x": 1, "y": 2}, ctx(), dev)
    assert dev.adb_calls[-1][3:5] == ("1", "2")


@pytest.mark.parametrize("step, ok", [
    ({"left": " 42 ", "right": "42"}, True),
    ({"left": "42", "right": "43"}, False),
    ({"left": "hello world", "right": "world", "mode": "contains"}, True),
    ({"left": "1,234.50", "right": "1234.5", "mode": "number"}, True),
    ({"left": "1234.6", "right": "1234.5", "mode": "number"}, False),
    ({"left": "1234.6", "right": "1234.5", "mode": "number", "tolerance": 0.01}, True),
    ({"left": "abc", "right": "1", "mode": "number"}, False),
    ({"left": "Total: 9 items", "right": r"\d+ items", "mode": "regex"}, True),
])
def test_compare(step, ok):
    c = ctx()
    if ok:
        dispatch({"action": "compare", **step}, c, Dev())
    else:
        with pytest.raises(StepFailedError, match="compare"):
            dispatch({"action": "compare", **step}, c, Dev())


def test_compare_rejects_unknown_mode_and_uses_message():
    with pytest.raises(ParamError):
        dispatch({"action": "compare", "left": 1, "right": 1, "mode": "fuzzy"}, ctx(), Dev())
    with pytest.raises(StepFailedError, match="display wrong"):
        dispatch({"action": "compare", "left": 1, "right": 2, "message": "display wrong"}, ctx(), Dev())


def test_for_each_maps_characters_and_interpolates_per_item():
    dev = Dev()
    c = ctx(expression="1 + 1")
    step = {"for_each": {"over": "{expression}=", "as": "ch", "skip": [" "], "strict": True,
                         "map": {"1": "1", "+": "plus", "=": "equals"},
                         "steps": [{"action": "tap_nth", "id": "app:id/btn_{{context.ch_mapped}}"}]}}
    resolved = interpolate(step, c)             # the runner's outer pass: {expression} resolved, {{...}} unescaped
    assert resolved["for_each"]["steps"][0]["id"] == "app:id/btn_{context.ch_mapped}"
    dispatch(resolved, c, dev)
    assert dev.taps == [(85, 425), (25, 425), (85, 425), (145, 425)]
    assert c.extras["ch"] == "=" and c.extras["ch_mapped"] == "equals"
    with pytest.raises(StepFailedError, match="no entry in map"):
        dispatch(interpolate(step, ctx(expression="2")), ctx(expression="2"), dev)
    with pytest.raises(ParamError, match="as:"):
        dispatch({"for_each": {"over": "ab", "steps": [{"action": "sleep", "duration_s": 0}]}}, c, dev)


def test_for_each_over_list_without_map():
    c = ctx(names=["a", "b"])
    seen = []
    from gitd.skills.engine.dispatch import register_step
    register_step("_record")(lambda step, ctx, device: seen.append(step["value"]))
    dispatch(interpolate({"for_each": {"over": "{names}", "as": "n", "steps": [{"action": "_record", "value": "{{context.n}}"}]}}, c), c, Dev())
    assert seen == ["a", "b"]
