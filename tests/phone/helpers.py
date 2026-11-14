"""Small UI-tree helpers shared by phone-CI tests (see conftest.py for fixtures)."""

import time


def screen_texts(dev) -> list[str]:
    """Visible text of every node in the current UI tree, top to bottom."""
    xml = dev.dump_xml()
    return [t for t in (dev.node_text(n) for n in dev.nodes(xml)) if t]


def edit_texts(dev) -> list[str]:
    """Current text of every EditText on screen (empty list if none)."""
    xml = dev.dump_xml()
    return [dev.node_text(n) for n in dev.nodes(xml) if 'class="android.widget.EditText"' in n]


# One uiautomator dump takes ~2-4 s locally and longer on a software-GPU CI runner
# (it waits for the UI to go idle), so poll windows must cover several dumps.
# A passing poll returns immediately; the timeout only bounds the failure case.
DEFAULT_TIMEOUT = 30.0


def _print_trace(name: str, trace: list[tuple[float, str]]):
    """Dump the per-poll history on timeout; pytest shows it under "Captured stdout"."""
    print(f"{name} timed out after {len(trace)} polls:")
    for t, value in trace:
        print(f"  +{t:5.1f}s  {value}")


def wait_until(predicate, timeout=DEFAULT_TIMEOUT, interval=0.5):
    """Poll predicate() until it returns a truthy value; return it, or the last value on timeout."""
    start = time.monotonic()
    deadline = start + timeout
    value = predicate()
    trace = [(0.0, repr(value)[:160])]
    while not value and time.monotonic() < deadline:
        time.sleep(interval)
        value = predicate()
        trace.append((time.monotonic() - start, repr(value)[:160]))
    if not value:
        _print_trace("wait_until", trace)
    return value


def wait_settled(dev, timeout=DEFAULT_TIMEOUT, interval=0.5, **locator) -> str | None:
    """Bounds of the node matching ``locator`` (find_bounds kwargs) once it stops moving.

    Settings re-lays out its header after first paint (e.g. an account avatar loads
    late), so a tap aimed at the first bounds can land on the old position.
    Returns None if the node never held still for two consecutive non-empty polls.
    """
    start = time.monotonic()
    deadline = start + timeout
    last = None
    trace = []
    while time.monotonic() < deadline:
        xml = dev.dump_xml()
        if not dev.nodes(xml):
            # dump_xml returns an empty hierarchy when uiautomator could not get an
            # idle state; that says nothing about the node, so keep the last reading.
            trace.append((time.monotonic() - start, "empty dump (UI not idle)"))
            time.sleep(interval)
            continue
        bounds = dev.find_bounds(xml, **locator)
        trace.append((time.monotonic() - start, bounds or "not found"))
        if bounds and bounds == last:
            return bounds
        last = bounds
        time.sleep(interval)
    _print_trace(f"wait_settled({locator})", trace)
    return None
