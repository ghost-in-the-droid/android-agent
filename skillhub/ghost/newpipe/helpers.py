"""Search-only NewPipe UI. No result opening, player, downloads or app-file reads."""
import re
import time
import xml.etree.ElementTree as ET
from gitd.bots.common.adb import input_text_arg
from gitd.skills.engine.os_popups import sweep_if_system_dialog

PKG = 'org.schabi.newpipe'
ID = PKG + ':id/'


def nodes(device):
    return [dict(n.attrib) for n in ET.fromstring(device.dump_xml()).iter('node')
            if n.get('enabled') != 'false' and n.get('bounds') != '[0,0][0,0]']


def pick(ns, rid):
    return next((n for n in ns if n.get('resource-id') == ID + rid), None)


def tap(device, node):
    if not node:
        raise ValueError('Requested NewPipe control is not visible')
    # A fast Portal snapshot may catch a preference row during scroll inertia.
    # Re-find this exact native control and require stable, on-screen bounds.
    identity = tuple(node.get(k, '') for k in ('resource-id', 'text', 'content-desc'))
    deadline = time.monotonic() + 5
    last = None
    while time.monotonic() < deadline:
        current = next((n for n in nodes(device) if tuple(n.get(k, '') for k in
                       ('resource-id', 'text', 'content-desc')) == identity), None)
        b = list(map(int, re.findall(r'-?\d+', current['bounds']))) if current else []
        visible = (len(b) == 4 and 0 <= b[0] < b[2] <= 1080
                   and 0 <= b[1] < b[3] <= 2340)
        if visible and b == last:
            focus = device.adb('shell', 'dumpsys window | grep -m1 mCurrentFocus')
            if PKG + '/' not in focus:
                raise ValueError('NewPipe does not own the focused window')
            device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
            return
        last = b if visible else None
        time.sleep(.25)
    raise ValueError('NewPipe control did not settle inside the tested display')


def wait(device, predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # A cold launch can request notifications after the runner's initial
        # sweep. Let the engine deny only that native permission, never grant.
        if sweep_if_system_dialog(device, {"deny_permissions": ["notifications"],
                "ignore": ["location", "contacts", "storage", "camera", "microphone",
                           "battery_optimization", "google_play_update", "keyboard_default",
                           "screen_recording", "immersive_mode_cling", "system_update"]}):
            continue
        ns = nodes(device)
        if any(n.get('text') == 'Check for updates' for n in ns):
            tap(device, next((n for n in ns if n.get('resource-id') == 'android:id/button2' and n.get('text') == 'NO'), None))
            continue
        if predicate(ns):
            return ns
        time.sleep(.4)
    raise ValueError('NewPipe did not reach the requested screen; network or UI changed')


def open_app(device, params, context):
    device.adb('shell', 'am', 'start', '-W', '-S', '-n', PKG + '/.MainActivity')
    def ready(ns):
        if any(n.get('text') == 'Keep Android Open' for n in ns):
            tap(device, next((n for n in ns if n.get('resource-id') == 'android:id/button1' and n.get('text') == 'OK'), None))
            return False
        if any(n.get('content-desc') == 'Open Drawer' for n in ns):
            return True
        return False
    wait(device, ready)
    return {'screen': 'home'}


def search(device, params, context):
    query = str(params['query']).strip()
    if not query or len(query) > 120 or not query.isascii() or any(ord(c) < 32 for c in query):
        raise ValueError('Use a nonempty ASCII query of at most 120 characters')
    open_app(device, params, context)
    tap(device, pick(nodes(device), 'action_search'))
    ns = wait(device, lambda ns: pick(ns, 'toolbar_search_edit_text') is not None)
    tap(device, pick(ns, 'toolbar_search_edit_text'))
    device.adb('shell', 'input', 'text', input_text_arg(query))
    device.press_enter()
    wait(device, lambda ns: pick(ns, 'itemVideoTitleView') is not None and pick(ns, 'toolbar_search_edit_text').get('text') == query)
    return read_results(device, {'limit': params.get('limit', 5)}, context)


def rows(ns):
    titles = [n for n in ns if n.get('resource-id') == ID + 'itemVideoTitleView']
    result = []
    for i, n in enumerate(titles):
        y = int(re.findall(r'\d+', n['bounds'])[1])
        bottom = int(re.findall(r'\d+', titles[i+1]['bounds'])[1]) if i+1 < len(titles) else 2205
        def value(rid):
            return next((m.get('text', '') for m in ns if m.get('resource-id') == ID + rid
                         and y <= int(re.findall(r'\d+', m['bounds'])[1]) < bottom), '')
        row = {'title': n.get('text', ''), 'channel': value('itemUploaderView'),
               'views_and_age': value('itemAdditionalDetails'), 'duration': value('itemDurationView')}
        if row['title'] and row['channel'] and row['views_and_age']:
            result.append(row)
    return result


def read_results(device, params, context):
    limit = int(params.get('limit', 5))
    if not 1 <= limit <= 7:
        raise ValueError('limit must be between 1 and 7 visible results')
    ns = nodes(device)
    if pick(ns, 'detail_video_title_view') or pick(ns, 'overlay_play_pause_button'):
        raise ValueError('Video detail/player screen is open; this skill reads search results only')
    field = pick(ns, 'toolbar_search_edit_text')
    result = rows(ns)[:limit]
    if not field or not field.get('text') or not result:
        raise ValueError('No public video search results visible')
    return {'query': field['text'], 'videos': result, 'count': len(result),
            'scope': 'visible search metadata only; no transcript or watched video'}


def home_ok(device, context):
    return context.result.get('screen') == 'home' and any(n.get('content-desc') == 'Open Drawer' for n in nodes(device))


def results_ok(device, context):
    try:
        actual = read_results(device, {'limit': len(context.result.get('videos', []))}, context)
        return actual == context.result and (not context.params.get('query') or actual['query'] == context.params['query'].strip())
    except (ValueError, ET.ParseError):
        return False


