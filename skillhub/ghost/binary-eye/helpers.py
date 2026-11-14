"""Binary Eye's generator only. No camera, files, clipboard, history or sharing."""
import re
import time
import xml.etree.ElementTree as ET
from gitd.bots.common.adb import input_text_arg
PKG = 'de.markusfisch.android.binaryeye'
ID = PKG + ':id/'
FORMATS = ('Aztec', 'Code 128', 'QR Code')

def nodes(device):
    return [dict(n.attrib) for n in ET.fromstring(device.dump_xml()).iter('node')
            if n.get('enabled') != 'false' and n.get('bounds') != '[0,0][0,0]']


def pick(ns, rid):
    return next((n for n in ns if n.get('resource-id') == ID + rid), None)


def tap(device, node):
    if not node:
        raise ValueError('Requested Binary Eye control is not visible')
    windows = device.adb('shell', 'dumpsys window')
    focus = next((line for line in windows.splitlines() if 'mCurrentFocus=' in line), '')
    if PKG + '/' not in focus:
        own_popup = 'PopupWindow' in focus and any('mFocusedApp=' in line and PKG + '/' in line for line in windows.splitlines())
        if not own_popup:
            raise ValueError('Binary Eye does not own the focused window')
        native = ET.fromstring(device.dump_xml(use_portal=False))
        if not any(n.get('package') == PKG and n.get('bounds') == node.get('bounds')
                   and n.get('text') == node.get('text') and n.get('resource-id') == node.get('resource-id') for n in native.iter('node')):
            raise ValueError('Format chooser target ownership could not be verified')
    b = list(map(int, re.findall(r'\d+', node['bounds'])))
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)


def wait(device, predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ns = nodes(device)
        if predicate(ns):
            return ns
        time.sleep(.4)
    raise ValueError('Binary Eye did not reach the requested screen; network or UI changed')


def inside(node, parent):
    a=list(map(int,re.findall(r'\d+',node['bounds'])));b=list(map(int,re.findall(r'\d+',parent['bounds'])))
    return b[0]<=a[0] and b[1]<=a[1] and a[2]<=b[2] and a[3]<=b[3]


def read_state(device, params, context):
    ns=nodes(device);image=pick(ns,'barcode')
    if image and image.get('content-desc')=='View barcode':
        return {'screen':'barcode','image_visible':True,'image_bounds':list(map(int,re.findall(r'\d+',image['bounds']))),
                'scope':'generated image viewer only; this action does not decode or scan the image'}
    field=pick(ns,'content');fmt=pick(ns,'format');escape=pick(ns,'unescape')
    if not field or not fmt or not escape or not pick(ns,'encode'):
        raise ValueError('Open Binary Eye generator or its generated image viewer')
    selected=next((n.get('text','') for n in ns if n.get('resource-id')=='android:id/text1' and inside(n,fmt)),None)
    if not selected:raise ValueError('Selected barcode format is not readable')
    return {'screen':'compose','displayed_content':field.get('text',''),'format':selected,
            'expand_escapes':escape.get('checked')=='true','scope':'current generator UI; empty field may display its input hint'}


def open_generator(device, params, context):
    device.adb('shell','am','start','-W','-f','0x04000000','-n',PKG+'/.activity.EncodeActivity')
    wait(device,lambda ns:pick(ns,'content') is not None and pick(ns,'encode') is not None)
    return read_state(device,{},context)


def set_content(device, params, context):
    content=str(params['content'])
    if not content or len(content)>512 or not content.isascii() or any(ord(c)<32 for c in content):
        raise ValueError('Use 1 to 512 printable ASCII characters; no control or escape sequences')
    state=read_state(device,{},context)
    if state['screen']!='compose':raise ValueError('Use edit_code or open_generator before entering content')
    ns=nodes(device)
    if pick(ns,'unescape').get('checked')=='true':tap(device,pick(ns,'unescape'))
    field=pick(nodes(device),'content');tap(device,field)
    device.adb('shell','input','keyevent','KEYCODE_MOVE_END',*(['KEYCODE_DEL']*(min(len(field.get('text','')),512)+2)))
    device.adb('shell','input','text',input_text_arg(content))
    if pick(nodes(device),'content').get('text')!=content:
        raise ValueError('Input did not read back exactly; no barcode generated')
    device.back()
    state=read_state(device,{},context)
    if state['displayed_content']!=content or state['expand_escapes']:
        raise ValueError('Literal content or escape-expansion state changed')
    return state


def set_format(device, params, context):
    wanted=str(params['format'])
    if wanted not in FORMATS:raise ValueError('Supported formats: Aztec, Code 128, QR Code')
    state=read_state(device,{},context)
    if state['screen']!='compose':raise ValueError('Open or edit the generator first')
    if state['format']==wanted:return state
    tap(device,pick(nodes(device),'format'))
    seen=set()
    for _ in range(8):
        ns=nodes(device)
        option=next((n for n in ns if n.get('resource-id')=='android:id/text1' and n.get('text')==wanted
                     and n.get('class')=='android.widget.CheckedTextView'),None)
        if option:
            tap(device,option);break
        choices=tuple(n.get('text','') for n in ns if n.get('class')=='android.widget.CheckedTextView')
        if choices in seen:raise ValueError('Requested format not visible in the bounded format list')
        seen.add(choices)
        listing=next((n for n in ns if n.get('class')=='android.widget.ListView'),None)
        if not listing:raise ValueError('Barcode format chooser is not visible')
        b=list(map(int,re.findall(r'\d+',listing['bounds'])));x=(b[0]+b[2])//2;pad=max(40,(b[3]-b[1])//8)
        # The supported list starts at Aztec. Returning to earlier items uses an upward-list swipe.
        down=wanted=='Aztec' or (wanted=='Code 128' and any(c in choices for c in ['QR Code','UPCA']))
        device.swipe(x,b[1]+pad if down else b[3]-pad,x,b[3]-pad if down else b[1]+pad,350)
    state=read_state(device,{},context)
    if state.get('format')!=wanted:raise ValueError('Barcode format did not read back exactly')
    return state


def generate(device, params, context):
    state=read_state(device,{},context)
    if state['screen']!='compose' or state.get('expand_escapes'):
        raise ValueError('Literal generator content is required; use set_content before encoding')
    tap(device,pick(nodes(device),'encode'))
    wait(device,lambda ns:pick(ns,'barcode') is not None)
    return {'screen':'barcode','image_visible':True,'generated_content':state['displayed_content'],'format':state['format'],
            'scope':'content read back before encoding; generated image visible; no camera or imported code'}


def generate_qr(device, params, context):
    open_generator(device,{},context)
    set_content(device,{'content':params['content']},context)
    set_format(device,{'format':'QR Code'},context)
    return generate(device,{},context)


def edit_code(device, params, context):
    if read_state(device,{},context)['screen']!='barcode':raise ValueError('A generator-created barcode viewer must be open')
    device.back();wait(device,lambda ns:pick(ns,'content') is not None and pick(ns,'encode') is not None)
    return read_state(device,{},context)


def state_ok(device, context):
    try:
        state=read_state(device,{},context)
        return state==context.result and (not context.params.get('content') or state.get('displayed_content')==context.params['content']) and (not context.params.get('format') or state.get('format')==context.params['format'])
    except (ValueError,ET.ParseError):return False


def generated_ok(device, context):
    try:
        return (read_state(device,{},context).get('screen')=='barcode' and context.result.get('image_visible') is True
                and bool(context.result.get('generated_content')) and context.result.get('format') in FORMATS
                and (not context.params.get('content') or (context.result['generated_content']==context.params['content'] and context.result['format']=='QR Code')))
    except (ValueError,ET.ParseError):return False
