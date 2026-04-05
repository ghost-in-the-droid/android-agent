"""Device context extraction — shared functions used by MCP tools, API endpoints,
and the Skill Creator. Single source of truth for all screen understanding primitives.

Usage:
    from gitd.services.device_context import (
        get_phone_state, get_screen_tree, get_interactive_elements,
        get_screen_xml, screenshot, screenshot_annotated, screenshot_cropped,
        ocr_screen, ocr_region, classify_screen,
    )
"""
import base64
import io
import json
import re
import subprocess
import urllib.request
from pathlib import Path

from gitd.bots.common.adb import Device, _stable_port


# ── Phone state ──────────────────────────────────────────────────────────────

def get_phone_state(device: str) -> dict:
    """Current app, package, activity, keyboard state, focused element.
    Uses Portal if available, falls back to dumpsys."""
    dev = Device(device)
    port = dev._ensure_portal_forward()
    if port:
        try:
            resp = json.loads(urllib.request.urlopen(
                f"http://localhost:{port}/phone_state", timeout=3).read())
            result = resp.get("result", {})
            if isinstance(result, str):
                result = json.loads(result)
            return result
        except Exception:
            pass
    # Fallback
    try:
        out = dev.adb("shell", "dumpsys", "window", "windows", timeout=5)
        m = re.search(r"mCurrentFocus.*?(\S+/\S+)", out)
        if m:
            pkg, activity = m.group(1).split("/", 1)
            return {"packageName": pkg, "activityName": activity, "currentApp": pkg.split(".")[-1]}
    except Exception:
        pass
    return {}


# ── Screenshots ──────────────────────────────────────────────────────────────

def screenshot(device: str, half_res: bool = True, quality: int = 50) -> dict:
    """Take screenshot via ADB screencap. Returns {image: base64, width, height}."""
    from PIL import Image
    raw = subprocess.check_output(
        ["adb", "-s", device, "exec-out", "screencap", "-p"], timeout=10)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    if half_res:
        img = img.resize((img.width // 2, img.height // 2), Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return {
        "image": base64.b64encode(buf.getvalue()).decode(),
        "width": img.width,
        "height": img.height,
    }


def screenshot_annotated(device: str) -> dict:
    """Screenshot with our own numbered element overlay drawn server-side.
    Each interactive element gets a colored badge with its index number.
    Returns {image: base64, width, height}."""
    from PIL import Image, ImageDraw, ImageFont

    # Take screenshot
    raw = subprocess.check_output(
        ["adb", "-s", device, "exec-out", "screencap", "-p"], timeout=10)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Get interactive elements
    elements = get_interactive_elements(device)

    # Color palette — distinct, vibrant
    COLORS = [
        (0, 229, 160),    # Ghost green (brand)
        (99, 102, 241),   # Indigo
        (56, 189, 248),   # Sky blue
        (251, 191, 36),   # Amber
        (167, 139, 250),  # Violet
        (52, 211, 153),   # Emerald
        (248, 113, 113),  # Red
        (96, 165, 250),   # Blue
    ]

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except Exception:
        font = ImageFont.load_default()
        font_sm = font

    for el in elements:
        idx = el["idx"]
        b = el["bounds"]
        x1, y1, x2, y2 = b["x1"], b["y1"], b["x2"], b["y2"]
        color = COLORS[idx % len(COLORS)]

        # Draw element border (thin, semi-transparent feel)
        for offset in range(2):
            draw.rectangle([x1 - offset, y1 - offset, x2 + offset, y2 + offset],
                           outline=color, width=1)

        # Draw index badge (top-left corner of element)
        label = str(idx)
        badge_w, badge_h = 24 + len(label) * 8, 24
        bx, by = x1, max(y1 - badge_h - 2, 0)

        # Badge background with slight rounding effect
        draw.rectangle([bx, by, bx + badge_w, by + badge_h], fill=color)
        # Badge text (white on color)
        draw.text((bx + 4, by + 1), label, fill=(255, 255, 255), font=font)

        # Optional: show element text label (truncated)
        text = el.get("text") or el.get("content_desc") or ""
        if text and len(text) < 30:
            label_x = bx + badge_w + 4
            draw.text((label_x, by + 3), text[:20], fill=color, font=font_sm)

    # Encode
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return {
        "image": base64.b64encode(buf.getvalue()).decode(),
        "width": img.width,
        "height": img.height,
    }


def screenshot_cropped(device: str, x1: int, y1: int, x2: int, y2: int,
                       quality: int = 70) -> dict:
    """Screenshot a specific region of the screen.
    Coordinates are in device pixels. Returns {image: base64, width, height}."""
    from PIL import Image
    raw = subprocess.check_output(
        ["adb", "-s", device, "exec-out", "screencap", "-p"], timeout=10)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    cropped = img.crop((x1, y1, x2, y2))
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=quality)
    return {
        "image": base64.b64encode(buf.getvalue()).decode(),
        "width": cropped.width,
        "height": cropped.height,
    }


# ── XML / Element tree ───────────────────────────────────────────────────────

def get_screen_xml(device: str, max_length: int = 50000) -> str:
    """Raw UI XML dump from uiautomator. Use get_screen_tree() for LLM-friendly format."""
    dev = Device(device)
    xml = dev.dump_xml()
    return xml[:max_length] if xml else ""


def get_interactive_elements(device: str, interactive_only: bool = True) -> list[dict]:
    """Interactive UI elements as a JSON-serializable list.
    Each element: {idx, text, content_desc, resource_id, class, bounds, center, clickable, scrollable}."""
    dev = Device(device)
    xml = dev.dump_xml()
    if not xml:
        return []

    elements = []
    for node in dev.nodes(xml):
        text = dev.node_text(node) or ""
        desc = dev.node_content_desc(node) or ""
        rid = dev.node_rid(node) or ""
        cls_m = re.search(r'class="([^"]*)"', node)
        cls = cls_m.group(1).split(".")[-1] if cls_m else ""
        clickable = 'clickable="true"' in node
        scrollable = 'scrollable="true"' in node

        if interactive_only and not clickable and not scrollable and not text and not desc:
            continue

        bounds = dev.node_bounds(node)
        if not bounds:
            continue
        x1, y1, x2, y2 = bounds
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

        elements.append({
            "idx": len(elements),
            "text": text,
            "content_desc": desc,
            "resource_id": rid.split("/")[-1] if "/" in rid else rid,
            "class": cls,
            "bounds": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            "center": {"x": cx, "y": cy},
            "clickable": clickable,
            "scrollable": scrollable,
        })
    return elements


def get_screen_tree(device: str, max_nodes: int = 80) -> str:
    """LLM-friendly indented UI hierarchy tree.

    Format per node:
      [idx] ClassName "label" [clickable,scrollable] [x1,y1][x2,y2]

    Skips deep non-interactive unlabelled nodes. Returns a string the LLM can
    read directly to understand screen layout and pick elements to interact with.
    """
    import xml.etree.ElementTree as ET
    dev = Device(device)
    xml_str = dev.dump_xml()
    if not xml_str:
        return "(empty screen)"

    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return "(XML parse error)"

    lines = []
    idx_counter = [0]

    def _walk(node, depth=0):
        if len(lines) >= max_nodes:
            return
        text_val = node.get("text", "") or ""
        desc = node.get("content-desc", "") or ""
        rid = node.get("resource-id", "") or ""
        cls = (node.get("class", "") or "").split(".")[-1]
        bounds = node.get("bounds", "")
        clickable = node.get("clickable", "") == "true"
        scrollable = node.get("scrollable", "") == "true"
        label = text_val or desc

        # Only show nodes the LLM can actually use:
        # - Has visible text/description, OR
        # - Is interactive (clickable/scrollable)
        # Skip pure layout containers (FrameLayout, LinearLayout, View with no label)
        is_useful = bool(label) or clickable or scrollable
        if not is_useful:
            # Still walk children — useful nodes may be nested inside containers
            for child in node:
                _walk(child, depth)
            return

        idx_counter[0] += 1
        idx = idx_counter[0]
        indent = "  " * min(depth, 6)
        flags = []
        if clickable:
            flags.append("clickable")
        if scrollable:
            flags.append("scrollable")
        flag_str = f" [{','.join(flags)}]" if flags else ""
        label_str = f' "{label}"' if label else ""
        # Show resource-id only for unlabelled interactive elements (helps identify buttons)
        rid_str = ""
        if not label and rid:
            rid_str = f' "{rid.split("/")[-1]}"'
        lines.append(f"{indent}[{idx}] {cls}{label_str}{rid_str}{flag_str} {bounds}")

        for child in node:
            _walk(child, depth + 1)

    for child in root:
        _walk(child, 0)

    return "\n".join(lines)


# ── OCR ──────────────────────────────────────────────────────────────────────

_ocr_engine = None


def _get_ocr():
    """Lazy-load RapidOCR (CPU, no GPU needed)."""
    global _ocr_engine
    if _ocr_engine is None:
        import logging
        logging.disable(logging.INFO)
        from rapidocr import RapidOCR
        _ocr_engine = RapidOCR()
        logging.disable(logging.NOTSET)
    return _ocr_engine


def ocr_screen(device: str) -> list[dict]:
    """OCR the full device screen. Returns [{text, conf, x, y}] sorted top-to-bottom."""
    raw = subprocess.check_output(
        ["adb", "-s", device, "exec-out", "screencap", "-p"], timeout=10)
    ocr = _get_ocr()
    result = ocr(raw)
    if not result or not result.txts:
        return []
    texts = []
    for box, txt, conf in zip(result.boxes, result.txts, result.scores):
        y, x = int(box[0][1]), int(box[0][0])
        w = int(box[2][0]) - x
        h = int(box[2][1]) - y
        texts.append({"text": txt, "conf": round(float(conf), 3), "x": x, "y": y, "w": w, "h": h})
    texts.sort(key=lambda t: t["y"])
    return texts


def ocr_region(device: str, x1: int, y1: int, x2: int, y2: int) -> list[dict]:
    """OCR a specific region of the screen. Coordinates in device pixels.
    Returns [{text, conf, x, y, w, h}] where x/y are relative to the crop."""
    from PIL import Image
    raw = subprocess.check_output(
        ["adb", "-s", device, "exec-out", "screencap", "-p"], timeout=10)
    img = Image.open(io.BytesIO(raw))
    cropped = img.crop((x1, y1, x2, y2))
    ocr = _get_ocr()
    result = ocr(cropped)
    if not result or not result.txts:
        return []
    texts = []
    for box, txt, conf in zip(result.boxes, result.txts, result.scores):
        ry, rx = int(box[0][1]), int(box[0][0])
        w = int(box[2][0]) - rx
        h = int(box[2][1]) - ry
        texts.append({"text": txt, "conf": round(float(conf), 3), "x": rx, "y": ry, "w": w, "h": h})
    texts.sort(key=lambda t: t["y"])
    return texts


# ── Overlay ──────────────────────────────────────────────────────────────────

def toggle_overlay(device: str, visible: bool = True) -> bool:
    """Toggle Portal's numbered element overlay. Returns True on success."""
    dev = Device(device)
    port = dev._ensure_portal_forward()
    if not port:
        return False
    try:
        payload = json.dumps({"visible": visible}).encode()
        req = urllib.request.Request(
            f"http://localhost:{port}/overlay", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


# ── Screen classification ────────────────────────────────────────────────────

def classify_screen(device: str) -> dict:
    """Classify the current screen state. Returns {app, screen_type, has_keyboard, details}.

    screen_type is one of: home, search, profile, settings, dialog, error, loading, unknown.
    Uses XML heuristics — no LLM needed."""
    state = get_phone_state(device)
    dev = Device(device)
    xml = dev.dump_xml() or ""

    pkg = state.get("packageName", "")
    app = state.get("currentApp", pkg.split(".")[-1] if pkg else "unknown")
    has_keyboard = state.get("keyboardVisible", False)

    # Heuristic classification
    screen_type = "unknown"
    details = {}

    # Launcher/home
    if "launcher" in pkg.lower() or "homescreen" in pkg.lower():
        screen_type = "launcher"
    # Dialog/popup detection
    elif any(w in xml for w in ["AlertDialog", "PopupWindow", 'content-desc="Close"', "Not now", "Cancel"]):
        screen_type = "dialog"
        # Try to get dialog text
        for node in dev.nodes(xml):
            text = dev.node_text(node) or ""
            if len(text) > 10 and 'clickable="false"' in node:
                details["dialog_text"] = text[:200]
                break
    # Error screen
    elif any(w in xml for w in ["error", "Error", "Something went wrong", "retry", "Try again"]):
        screen_type = "error"
    # Loading
    elif any(w in xml for w in ["ProgressBar", "Loading", "Please wait"]):
        screen_type = "loading"
    # Search
    elif has_keyboard or any(w in xml for w in ["EditText", "search_bar", "SearchView"]):
        screen_type = "search"
    # Settings
    elif "settings" in pkg.lower() or "Settings" in xml[:500]:
        screen_type = "settings"
    # Profile (TikTok/Instagram specific)
    elif any(w in xml for w in ["Following", "Followers", "follower"]):
        screen_type = "profile"
    # Home/feed
    elif any(w in xml for w in ["RecyclerView", "ViewPager", "feed"]):
        screen_type = "feed"

    return {
        "app": app,
        "package": pkg,
        "screen_type": screen_type,
        "has_keyboard": has_keyboard,
        "activity": state.get("activityName", ""),
        "details": details,
    }


# ── Clipboard ────────────────────────────────────────────────────────────────

def clipboard_get(device: str) -> str:
    """Get current clipboard text from device."""
    dev = Device(device)
    try:
        return dev.adb("shell", "am", "broadcast", "-a", "clipper.get", timeout=3).strip()
    except Exception:
        # Fallback: use service call
        try:
            out = dev.adb("shell", "service", "call", "clipboard", "2", "i32", "1", timeout=3)
            # Parse service call output
            text = re.findall(r"'(.+?)'", out)
            return "".join(text).replace("\n", "").strip() if text else ""
        except Exception:
            return ""


def clipboard_set(device: str, text: str) -> bool:
    """Set clipboard text on device."""
    dev = Device(device)
    try:
        dev.adb("shell", "am", "broadcast", "-a", "clipper.set", "-e", "text", text, timeout=3)
        return True
    except Exception:
        return False


# ── Notifications ────────────────────────────────────────────────────────────

def get_notifications(device: str) -> list[dict]:
    """Get active notifications from the notification panel.
    Returns [{package, title, text, time}]."""
    dev = Device(device)
    try:
        out = dev.adb("shell", "dumpsys", "notification", "--noredact", timeout=10)
    except Exception:
        return []
    notifications = []
    current = {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("pkg="):
            if current:
                notifications.append(current)
            current = {"package": re.search(r"pkg=(\S+)", line).group(1) if "pkg=" in line else ""}
        if "android.title=" in line:
            m = re.search(r"android\.title=String \((.+?)\)", line)
            if m:
                current["title"] = m.group(1)
        if "android.text=" in line:
            m = re.search(r"android\.text=String \((.+?)\)", line)
            if m:
                current["text"] = m.group(1)
    if current and current.get("package"):
        notifications.append(current)
    return notifications


def open_notifications(device: str) -> bool:
    """Pull down the notification shade."""
    dev = Device(device)
    try:
        dev.adb("shell", "cmd", "statusbar", "expand-notifications", timeout=3)
        return True
    except Exception:
        return False


def clear_notifications(device: str) -> bool:
    """Dismiss all notifications."""
    dev = Device(device)
    try:
        dev.adb("shell", "service", "call", "notification", "1", timeout=3)
        return True
    except Exception:
        return False


# ── Intent launching ─────────────────────────────────────────────────────────

def launch_intent(device: str, action: str = "", data: str = "", package: str = "",
                  component: str = "", extras: dict | None = None) -> str:
    """Launch a full Android intent. More powerful than launch_app().
    Examples:
      launch_intent(dev, action="android.intent.action.VIEW", data="https://google.com")
      launch_intent(dev, package="com.android.settings", component=".Settings")
    """
    dev = Device(device)
    cmd = ["shell", "am", "start"]
    if action:
        cmd.extend(["-a", action])
    if data:
        cmd.extend(["-d", data])
    if package and component:
        cmd.extend(["-n", f"{package}/{component}"])
    elif package:
        cmd.extend(["-p", package])
    if extras:
        for k, v in extras.items():
            if isinstance(v, bool):
                cmd.extend(["--ez", k, str(v).lower()])
            elif isinstance(v, int):
                cmd.extend(["--ei", k, str(v)])
            else:
                cmd.extend(["--es", k, str(v)])
    try:
        return dev.adb(*cmd, timeout=5)
    except Exception as e:
        return f"Error: {e}"


# ── Search / find on screen ──────────────────────────────────────────────────

def find_on_screen(device: str, text: str) -> dict | None:
    """Find specific text on screen and return its location.
    Searches XML elements first (fast), falls back to OCR (slower).
    Returns {text, x, y, w, h, method} or None if not found."""
    dev = Device(device)
    xml = dev.dump_xml()
    if xml:
        # Search in XML text + content-desc
        for node in dev.nodes(xml):
            node_text = dev.node_text(node) or ""
            node_desc = dev.node_content_desc(node) or ""
            if text.lower() in node_text.lower() or text.lower() in node_desc.lower():
                bounds = dev.node_bounds(node)
                if bounds:
                    x1, y1, x2, y2 = bounds
                    return {"text": node_text or node_desc, "x": (x1 + x2) // 2,
                            "y": (y1 + y2) // 2, "w": x2 - x1, "h": y2 - y1, "method": "xml"}
    # Fallback to OCR
    try:
        texts = ocr_screen(device)
        for t in texts:
            if text.lower() in t["text"].lower():
                return {"text": t["text"], "x": t["x"] + t.get("w", 0) // 2,
                        "y": t["y"] + t.get("h", 0) // 2,
                        "w": t.get("w", 0), "h": t.get("h", 0), "method": "ocr"}
    except Exception:
        pass
    return None


# ── Convenience: build full context for LLM ─────────────────────────────────

def build_llm_context(device: str, include_screenshot: bool = True,
                      include_ocr: bool = False, max_elements: int = 40) -> dict:
    """Build a complete context snapshot for an LLM agent.

    Returns a dict with all context an agent needs to understand and act on the screen.
    Used by Skill Creator and can be used by any agent integration."""
    ctx = {
        "phone_state": get_phone_state(device),
        "screen_type": classify_screen(device),
        "elements": get_interactive_elements(device)[:max_elements],
        "screen_tree": get_screen_tree(device),
    }
    if include_screenshot:
        ctx["screenshot"] = screenshot(device)
    if include_ocr:
        ctx["ocr"] = ocr_screen(device)
    return ctx


# ── Device health check ──────────────────────────────────────────────────────

def device_health(device: str) -> dict:
    """Comprehensive device health check. Returns status for every subsystem."""
    dev = Device(device)
    health = {"serial": device}

    # Connection
    health["connection"] = {"type": "usb", "status": "connected"}

    # Portal
    portal = {"installed": False, "service_active": False, "http_responding": False}
    try:
        ps = subprocess.run(["adb", "-s", device, "shell", "pm", "list", "packages"],
                            capture_output=True, text=True, timeout=5)
        portal["installed"] = "com.ghostinthedroid.portal" in ps.stdout or "com.droidrun.portal" in ps.stdout
    except Exception:
        pass
    try:
        acc = subprocess.run(["adb", "-s", device, "shell", "settings", "get", "secure",
                              "enabled_accessibility_services"],
                             capture_output=True, text=True, timeout=5)
        portal["service_active"] = "com.ghostinthedroid.portal" in acc.stdout or "com.droidrun.portal" in acc.stdout
    except Exception:
        pass
    if portal["service_active"]:
        port = dev._ensure_portal_forward()
        if port:
            try:
                urllib.request.urlopen(f"http://localhost:{port}/version", timeout=2)
                portal["http_responding"] = True
            except Exception:
                pass
    health["portal"] = portal

    # WiFi
    wifi = {"connected": False, "ip": None, "ssid": None}
    try:
        route = dev.adb("shell", "ip", "route", timeout=3)
        m = re.search(r"src (\d+\.\d+\.\d+\.\d+)", route)
        if m:
            wifi["connected"] = True
            wifi["ip"] = m.group(1)
        ssid_out = dev.adb("shell", "dumpsys", "wifi", timeout=5)
        m2 = re.search(r'mWifiInfo.*?SSID: "?([^",\n]+)"?', ssid_out)
        if m2:
            wifi["ssid"] = m2.group(1).strip('"')
    except Exception:
        pass
    health["wifi"] = wifi

    # Battery
    battery = {"level": -1, "charging": False}
    try:
        batt = dev.adb("shell", "dumpsys", "battery", timeout=5)
        m_level = re.search(r"level:\s*(\d+)", batt)
        if m_level:
            battery["level"] = int(m_level.group(1))
        battery["charging"] = "AC powered: true" in batt or "USB powered: true" in batt
    except Exception:
        pass
    health["battery"] = battery

    # Storage
    storage = {"free_mb": -1, "total_mb": -1}
    try:
        df = dev.adb("shell", "df", "/data", timeout=5)
        # Parse df output — second line has the values
        lines = [l for l in df.strip().splitlines() if "/data" in l]
        if lines:
            parts = lines[0].split()
            if len(parts) >= 4:
                # Values might be in KB or 1K-blocks
                total_kb = int(parts[1]) if parts[1].isdigit() else 0
                free_kb = int(parts[3]) if parts[3].isdigit() else 0
                storage["total_mb"] = total_kb // 1024
                storage["free_mb"] = free_kb // 1024
    except Exception:
        pass
    health["storage"] = storage

    # Device info
    info = {}
    props = {
        "model": "ro.product.model",
        "brand": "ro.product.brand",
        "android_version": "ro.build.version.release",
        "api_level": "ro.build.version.sdk",
    }
    for key, prop in props.items():
        try:
            info[key] = dev.adb("shell", "getprop", prop, timeout=3).strip()
        except Exception:
            info[key] = ""
    try:
        wm = dev.adb("shell", "wm", "size", timeout=3)
        m = re.search(r"(\d+x\d+)", wm)
        info["screen"] = m.group(1) if m else ""
    except Exception:
        info["screen"] = ""
    health["device_info"] = info

    # Target apps
    apps = {}
    target_packages = [
        ("com.zhiliaoapp.musically", "TikTok"),
        ("com.instagram.android", "Instagram"),
        ("com.google.android.gm", "Gmail"),
        ("com.android.chrome", "Chrome"),
    ]
    for pkg, name in target_packages:
        try:
            ver = dev.get_app_version(pkg)
            apps[pkg] = {"installed": bool(ver), "version": ver or "", "name": name}
        except Exception:
            apps[pkg] = {"installed": False, "version": "", "name": name}
    health["apps"] = apps

    # Keyboard
    try:
        kbd = dev.adb("shell", "settings", "get", "secure", "default_input_method", timeout=3).strip()
        health["keyboard"] = kbd
    except Exception:
        health["keyboard"] = ""

    # Screen state
    try:
        power = dev.adb("shell", "dumpsys", "power", timeout=5)
        health["screen_on"] = "mWakefulness=Awake" in power or "Display Power: state=ON" in power
    except Exception:
        health["screen_on"] = True

    return health


# ── Wireless ADB ─────────────────────────────────────────────────────────────

def get_device_wifi_ip(device: str) -> str | None:
    """Get the WiFi IP address of a USB-connected device."""
    dev = Device(device)
    try:
        route = dev.adb("shell", "ip", "route", timeout=3)
        m = re.search(r"src (\d+\.\d+\.\d+\.\d+)", route)
        return m.group(1) if m else None
    except Exception:
        return None


def wireless_enable(device: str) -> dict:
    """Switch a USB device to WiFi mode (tcpip). Returns {ok, wifi_ip, wifi_port}."""
    ip = get_device_wifi_ip(device)
    if not ip:
        return {"ok": False, "error": "Cannot detect WiFi IP — is WiFi connected?"}
    try:
        subprocess.run(["adb", "-s", device, "tcpip", "5555"],
                       capture_output=True, text=True, timeout=5, check=True)
    except Exception as e:
        return {"ok": False, "error": f"tcpip failed: {e}"}
    import time
    time.sleep(2)
    try:
        result = subprocess.run(["adb", "connect", f"{ip}:5555"],
                                capture_output=True, text=True, timeout=5)
        if "connected" in result.stdout.lower() or "already" in result.stdout.lower():
            return {"ok": True, "wifi_ip": ip, "wifi_port": 5555}
        return {"ok": False, "error": result.stdout.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def wireless_pair(ip: str, port: int, code: str) -> dict:
    """Pair with a device using Wireless Debugging (Android 11+).
    Returns {ok, device_serial}."""
    try:
        result = subprocess.run(["adb", "pair", f"{ip}:{port}", code],
                                capture_output=True, text=True, timeout=10)
        if "successfully" in result.stdout.lower():
            # Now connect
            return wireless_connect(ip, 5555)
        return {"ok": False, "error": result.stdout.strip() or result.stderr.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def wireless_connect(ip: str, port: int = 5555) -> dict:
    """Connect to a device over WiFi. Returns {ok, device_serial}."""
    try:
        result = subprocess.run(["adb", "connect", f"{ip}:{port}"],
                                capture_output=True, text=True, timeout=5)
        out = result.stdout.strip()
        if "connected" in out.lower() or "already" in out.lower():
            return {"ok": True, "device_serial": f"{ip}:{port}"}
        return {"ok": False, "error": out}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def wireless_disconnect(device: str) -> dict:
    """Disconnect a wireless device."""
    try:
        result = subprocess.run(["adb", "disconnect", device],
                                capture_output=True, text=True, timeout=5)
        return {"ok": True, "message": result.stdout.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def wireless_reconnect_all() -> list[dict]:
    """Reconnect all known WiFi devices from DB. Called on server startup."""
    results = []
    try:
        from gitd.models.base import SessionLocal
        from gitd.models.phone import Phone
        db = SessionLocal()
        wifi_phones = db.query(Phone).filter(
            Phone.connection_type.in_(["wifi", "wireless_debug"]),
            Phone.wifi_ip.isnot(None),
        ).all()
        for phone in wifi_phones:
            r = wireless_connect(phone.wifi_ip, phone.wifi_port or 5555)
            results.append({"serial": phone.serial, "ip": phone.wifi_ip, **r})
        db.close()
    except Exception:
        pass
    return results


# ── Structural fingerprint ───────────────────────────────────────────────────

def fingerprint_screen(device: str) -> dict:
    """Structural fingerprint of current screen — stable regardless of visual changes.
    Uses UI structure, not pixels."""
    state = get_phone_state(device)
    elements = get_interactive_elements(device)

    pkg = state.get("packageName", "")
    activity = state.get("activityName", "")

    return {
        "package": pkg,
        "activity": activity,
        "screen_type": classify_screen(device).get("screen_type", "unknown"),
        "is_launcher": "launcher" in activity.lower() if activity else False,
        "has_keyboard": state.get("keyboardVisible", False),
        "interactive_count": len(elements),
        "element_signatures": [
            f"{e.get('class', '')}.{e.get('resource_id', '')}"
            for e in elements[:20]
        ],
        "hash": _fingerprint_hash(pkg, activity, elements),
    }


def _fingerprint_hash(pkg: str, activity: str, elements: list[dict]) -> str:
    """Stable hash of screen structure — use for change detection."""
    import hashlib
    sig = f"{pkg}|{activity}|{len(elements)}|"
    sig += "|".join(f"{e.get('class','')}.{e.get('resource_id','')}" for e in elements[:20])
    return hashlib.md5(sig.encode()).hexdigest()[:12]


def validate_fingerprint(device: str, expected: dict) -> dict:
    """Compare current screen against an expected fingerprint.
    Returns {valid: bool, mismatches: [...]}."""
    current = fingerprint_screen(device)
    mismatches = []
    for key in ("package", "activity", "screen_type", "is_launcher"):
        if key in expected and current.get(key) != expected[key]:
            mismatches.append({"field": key, "expected": expected[key], "actual": current.get(key)})
    return {"valid": len(mismatches) == 0, "mismatches": mismatches, "current": current}
