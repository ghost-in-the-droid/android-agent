"""Validator kind dispatch — end_state_validator: primitives + composition.

Composition:
    {all_of: [<v>, <v>, ...]}    → AND
    {any_of: [<v>, <v>, ...]}    → OR
    {not: <v>}                    → NOT
    A bare list (no all_of key)  → treated as all_of

Primitives (see docs/skill-schema-v2.md §4):
    text_visible       — a11y tree substring
    element_present    — id/desc/xpath present in a11y tree
    url_contains       — WebView URL substring
    pixel_at           — screencap pixel RGB match ± tolerance
    ocr_text_present   — RapidOCR on screencap (optional region)
    screen_hash        — perceptual hash match against reference
    custom_python      — user-supplied predicate `fn(device, context) -> bool`

Pluggable: `@register_validator("my_kind")` for third-party primitives.

Signature:
    def validator(spec: dict, ctx: RunContext, device) -> bool
        # Return True iff satisfied; may raise on malformed spec.
"""

from __future__ import annotations

import logging
import re
from typing import Callable

from gitd.skills.engine.context import RunContext
from gitd.skills.engine.errors import (
    DispatchError,
    ParamError,
    UnknownValidatorKindError,
)

from . import privacy

log = logging.getLogger("skills.engine.validators")

_VALIDATORS: dict[str, Callable[[dict, RunContext, object], bool]] = {}


def register_validator(kind: str) -> Callable[[Callable], Callable]:
    def wrap(fn):
        if kind in _VALIDATORS:
            log.warning("Overriding registered validator kind %r", kind)
        _VALIDATORS[kind] = fn
        return fn

    return wrap


def evaluate(spec: dict | list, ctx: RunContext, device) -> bool:
    """Evaluate a validator spec (composable). Returns bool."""
    privacy.guard_validator(spec)
    if spec is None:
        return True

    if isinstance(spec, list):
        # Bare list = all_of
        return all(evaluate(s, ctx, device) for s in spec)

    if not isinstance(spec, dict):
        raise ParamError(f"Validator spec must be dict or list, got {type(spec).__name__}")

    # Composition operators
    if "all_of" in spec:
        subs = spec["all_of"]
        return all(evaluate(s, ctx, device) for s in subs)
    if "any_of" in spec:
        subs = spec["any_of"]
        return any(evaluate(s, ctx, device) for s in subs)
    if "not" in spec:
        return not evaluate(spec["not"], ctx, device)

    # Leaf: must have kind:
    kind = spec.get("kind")
    if not kind:
        raise ParamError(
            "Validator leaf spec missing `kind:`",
            payload={"spec": spec},
            hint="Leaf validators need one of: text_visible, element_present, url_contains, pixel_at, ocr_text_present, screen_hash, custom_python",
        )
    fn = _VALIDATORS.get(kind)
    if fn is None:
        raise UnknownValidatorKindError(
            f"Unknown validator kind: {kind!r}",
            hint=f"Registered kinds: {sorted(_VALIDATORS.keys())}",
        )
    return bool(fn(spec, ctx, device))


# ═══════════════════════════════════════════════════════════════════════════
# Built-in validators
# ═══════════════════════════════════════════════════════════════════════════


@register_validator("text_visible")
def _text_visible(spec, ctx, device) -> bool:
    text = spec.get("text", "")
    if not text:
        raise ParamError("text_visible: `text:` required")
    xml = privacy.dump_xml(device)
    if spec.get("exact"):
        return f'text="{text}"' in xml or f'content-desc="{text}"' in xml
    return text in xml


@register_validator("element_present")
def _element_present(spec, ctx, device) -> bool:
    xml = privacy.dump_xml(device)
    for locator, attr in (("id", "resource-id"), ("desc", "content-desc"), ("text", "text")):
        target = spec.get(locator)
        if not target:
            continue
        pat = re.compile(rf'<node[^>]*{attr}="{re.escape(target)}"')
        if pat.search(xml):
            return True
        return False
    if spec.get("xpath"):
        raise ParamError("element_present: xpath support pending — use id/desc/text")
    raise ParamError("element_present: one of id/desc/text/xpath required")


@register_validator("url_contains")
def _url_contains(spec, ctx, device) -> bool:
    substring = spec.get("substring", "")
    if not substring:
        raise ParamError("url_contains: `substring:` required")
    # Read current URL from WebView / Chrome via a11y tree (Chrome exposes it as content-desc on the URL bar)
    xml = privacy.dump_xml(device)
    # Locate the address-bar node first: the accessibility reader emits text
    # before resource-id, while other dumps can use the opposite order.
    node = re.search(r'<node\b[^>]*\sresource-id="com\.android\.chrome:id/url_bar"[^>]*>', xml)
    m = re.search(r'\stext="([^"]*)"', node.group(0)) if node else None
    if not m:
        # Chrome may hide the URL bar; try content-desc
        m = re.search(r'content-desc="([^"]*://[^"]*)"', xml)
    if not m:
        return False
    return substring in m.group(1)


@register_validator("pixel_at")
def _pixel_at(spec, ctx, device) -> bool:
    x, y = spec.get("x"), spec.get("y")
    rgb = spec.get("rgb")
    if x is None or y is None or not rgb:
        raise ParamError("pixel_at: x, y, rgb required")
    tolerance = int(spec.get("tolerance", 8))

    try:
        from PIL import Image
    except ImportError:
        raise DispatchError("pixel_at requires PIL — pip install pillow")

    import io

    remote = "/sdcard/_ghost_pixel_check.png"
    device.adb("shell", "screencap", "-p", remote)
    png_bytes = device.adb("exec-out", "cat", remote, binary=True) if hasattr(device, "adb") else None
    # Fallback: pull the file
    if png_bytes is None:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            local = f.name
        device.adb("pull", remote, local)
        img = Image.open(local).convert("RGB")
    else:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")

    r, g, b = img.getpixel((int(x), int(y)))
    tr, tg, tb = rgb
    return abs(r - tr) <= tolerance and abs(g - tg) <= tolerance and abs(b - tb) <= tolerance


@register_validator("ocr_text_present")
def _ocr_text_present(spec, ctx, device) -> bool:
    text = spec.get("text", "")
    if not text:
        raise ParamError("ocr_text_present: `text:` required")
    region = spec.get("region")  # {x, y, w, h} optional

    try:
        from rapidocr import RapidOCR
    except ImportError:
        raise DispatchError(
            "ocr_text_present requires rapidocr — pip install rapidocr",
            hint="Or use text_visible if the text is exposed in the a11y tree.",
        )

    remote = "/sdcard/_ghost_ocr_check.png"
    device.adb("shell", "screencap", "-p", remote)
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        local = f.name
    device.adb("pull", remote, local)

    ocr = RapidOCR()
    result, _ = ocr(local)
    if not result:
        return False

    for _bbox, ocr_text, _score in result:
        if region:
            # bbox is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]; get bounding rect
            xs = [pt[0] for pt in _bbox]
            ys = [pt[1] for pt in _bbox]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            if not (
                region["x"] <= x_min
                and x_max <= region["x"] + region["w"]
                and region["y"] <= y_min
                and y_max <= region["y"] + region["h"]
            ):
                continue
        if text in ocr_text:
            return True
    return False


@register_validator("screen_hash")
def _screen_hash(spec, ctx, device) -> bool:
    ref_hash = spec.get("ref_hash", "")
    if not ref_hash:
        raise ParamError("screen_hash: `ref_hash:` required")
    similarity_min = float(spec.get("similarity_min", 0.85))
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        raise DispatchError("screen_hash requires imagehash + pillow — pip install imagehash pillow")

    remote = "/sdcard/_ghost_hash_check.png"
    device.adb("shell", "screencap", "-p", remote)
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        local = f.name
    device.adb("pull", remote, local)
    img = Image.open(local)
    cur_hash = imagehash.phash(img)
    ref = imagehash.hex_to_hash(ref_hash)
    # phash returns Hamming distance; convert to similarity
    dist = cur_hash - ref
    max_dist = len(cur_hash.hash) ** 2  # 64 for 8x8 phash
    similarity = 1.0 - (dist / max_dist)
    return similarity >= similarity_min


@register_validator("custom_python")
def _custom_python(spec, ctx, device) -> bool:
    ref = spec.get("function") or spec.get("module") + ":" + spec.get("name", "") if spec.get("module") else ""
    ref = spec.get("function", ref)
    if not ref or ":" not in ref:
        raise ParamError(
            "custom_python: `function:` must be `<file>:<function>` (e.g. validators:handle_ok)",
            payload={"spec": spec},
        )
    from gitd.skills.engine.pyimport import identity_from_ctx, resolve_callable

    fn = resolve_callable(ref, identity_from_ctx(ctx), what="custom_python")
    try:
        return bool(fn(device, ctx))
    except Exception as e:
        raise DispatchError(f"custom_python {ref} raised {type(e).__name__}: {e}") from e


# ═══════════════════════════════════════════════════════════════════════════


def registered_kinds() -> list[str]:
    return sorted(_VALIDATORS.keys())
