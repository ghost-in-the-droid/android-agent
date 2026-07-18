"""Tests for ascii_typeable — the adb `input text` transliteration guard."""

import pytest

from gitd.bots.common.adb import ascii_typeable


def test_plain_ascii_unchanged():
    assert ascii_typeable("hello world") == "hello world"
    assert ascii_typeable("Search #cats 123!") == "Search #cats 123!"
    assert ascii_typeable("") == ""


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Sauté", "Saute"),
        ("café", "cafe"),
        ("naïve résumé", "naive resume"),
        ("Zürich", "Zurich"),
        ("piñata", "pinata"),
        ("Málaga", "Malaga"),
    ],
)
def test_accents_decomposed_to_base_letter(raw, expected):
    assert ascii_typeable(raw) == expected


def test_result_is_always_ascii():
    for s in ["Sauté", "日本語", "😀 emoji", "Ω mix café"]:
        assert ascii_typeable(s).isascii()


def test_untypeable_glyphs_dropped_not_erroring():
    # CJK / emoji have no ASCII base form → dropped (type_unicode is the path
    # for those); the guard must never raise, just return what it can.
    assert ascii_typeable("日本語") == ""
    assert ascii_typeable("café 😀") == "cafe "


def test_ascii_fast_path_is_identity():
    s = "already ascii, no change"
    assert ascii_typeable(s) is s  # isascii() short-circuit returns the same object
