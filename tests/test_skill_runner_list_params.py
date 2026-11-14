"""CLI passes strings; list[str] params must coerce from JSON, bracketed or bare comma lists."""
import pytest
from gitd.skills.engine.loader import Param
from gitd.skills.engine.runner import _resolve_params


def _p():
    kw = {"name": "tags", "type": "list[str]"}
    try:
        return [Param(**kw, required=False, default=[])]
    except TypeError:
        return [Param(**kw)]


@pytest.mark.parametrize("raw,expected", [
    ("[cat,fyp]", ["cat", "fyp"]),
    ("cat, fyp", ["cat", "fyp"]),
    ('["cat","fyp"]', ["cat", "fyp"]),
    ("[]", []),
    (["x"], ["x"]),
])
def test_list_str_coercion(raw, expected):
    assert _resolve_params(_p(), {"tags": raw}, "s", "a")["tags"] == expected
