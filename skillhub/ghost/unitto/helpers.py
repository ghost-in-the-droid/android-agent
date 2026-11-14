"""Read Unitto's displayed length conversions; no currency or personal tools."""
import re
import time
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from gitd.bots.common.adb import input_text_arg

PKG='com.sadellie.unitto'
# Exact SI definitions, meters per unit. Used only to validate the app's UI result.
FACTORS={'Millimeter':Decimal('.001'),'Centimeter':Decimal('.01'),'Meter':Decimal(1),'Kilometer':Decimal(1000),'Inch':Decimal('.0254'),'Yard':Decimal('.9144'),'Mile':Decimal('1609.344')}
SYMBOLS={'mm':'Millimeter','cm':'Centimeter','m':'Meter','km':'Kilometer','in':'Inch','yd':'Yard','Mi':'Mile'}

def foreground(device):
    raw=device.adb('shell','dumpsys','window')
    focus=next((s for s in raw.splitlines() if 'mCurrentFocus=' in s),'')
    if PKG+'/' not in focus:raise ValueError('Unitto does not own the focused window; input aborted')

def nodes(device):
    foreground(device)
    root=ET.fromstring(device.dump_xml(use_portal=False))
    foreground(device)
    return [dict(n.attrib) for n in root.iter('node') if n.get('package')==PKG and n.get('enabled')!='false' and n.get('bounds')!='[0,0][0,0]']

def box(n):return list(map(int,re.findall(r'\d+',n['bounds'])))
def find(ns,s):return next((n for n in ns if s in [n.get('text'),n.get('content-desc')] and n.get('class')!='android.widget.EditText'),None)
def tap(device,n):
    if n is None:raise ValueError('Required Unitto control is missing')
    foreground(device);a=box(n);device.tap((a[0]+a[2])//2,(a[1]+a[3])//2)

def wait(device,predicate):
    until=time.monotonic()+20
    while time.monotonic()<until:
        ns=nodes(device)
        if predicate(ns):return ns
        time.sleep(.3)
    raise ValueError('Unitto did not reach the requested converter screen')

def number(text):
    clean=re.sub(r'[\s\u202f]','',text).replace('−','-')
    if not re.fullmatch(r'-?\d+(?:\.\d+)?',clean):raise ValueError('Displayed value is not a plain finite decimal')
    return Decimal(clean)

def value_param(value):
    text=str(value)
    if not re.fullmatch(r'\d{1,9}(?:\.\d{1,6})?',text):raise ValueError('Use a nonnegative plain decimal: up to 9 integer and 6 fractional digits')
    return text

def read_state(device,params,context):
    ns=nodes(device)
    if not find(ns,'Swap units'):raise ValueError('Open the Unitto converter first')
    fields=sorted([n for n in ns if n.get('class')=='android.widget.EditText'],key=lambda n:box(n)[1])
    if len(fields)!=2:raise ValueError('Expected exactly two converter numeric fields')
    values=[];units=[]
    for field in fields:
        text=field.get('text','')
        if not text:
            text=next((n.get('text') for n in ns if n.get('class')=='android.widget.TextView' and n.get('bounds')==field['bounds']),None)
        if text is None:raise ValueError('Numeric field is not readable')
        values.append((text,number(text)))
        below=sorted([n for n in ns if n.get('class')=='android.widget.TextView' and box(n)[1]>=box(field)[3] and n.get('text') in SYMBOLS],key=lambda n:box(n)[1])
        if not below:raise ValueError('Displayed length unit is not supported')
        units.append(SYMBOLS[below[0]['text']])
    return {'screen':'length_converter','from_unit':units[0],'to_unit':units[1], 'input_display':values[0][0],'output_display':values[1][0],'input_value':str(values[0][1]),'output_value':str(values[1][1]),'scope':'current displayed physical length conversion; output rounded by Unitto'}

def open_converter(device,params,context):
    raw=device.adb('shell','dumpsys','package',PKG)
    if not re.search(r'\bversionCode=76\b',raw):raise ValueError('Only Unitto version code 76 (Titanium yellow) has been tested')
    device.adb('shell','am','start','-W','-a','android.intent.action.MAIN','-c','android.intent.category.LAUNCHER','-n',PKG+'/.MainActivity')
    ns=wait(device,lambda ns:find(ns,'Open menu') is not None)
    if not find(ns,'Swap units'):
        tap(device,find(ns,'Open menu'));ns=wait(device,lambda ns:find(ns,'Unit converter') is not None);tap(device,find(ns,'Unit converter'))
    wait(device,lambda ns:find(ns,'Swap units') is not None)
    return read_state(device,{},context)

def choose_unit(device,unit,side):
    if unit not in FACTORS:raise ValueError('Supported length units: '+', '.join(FACTORS))
    ns=nodes(device);swap=find(ns,'Swap units')
    if not swap:raise ValueError('Open Unitto converter first')
    # Unit labels share the swap row; locate by semantic row and side, never a blind screen tap.
    controls=[n for n in ns if n.get('class')=='android.widget.TextView' and abs(box(n)[1]-box(swap)[1])<25 and ((box(n)[0]<box(swap)[0]) if side=='from_unit' else (box(n)[0]>box(swap)[2]))]
    if len(controls)!=1:raise ValueError('Unit selector row is ambiguous')
    tap(device,controls[0]);ns=wait(device,lambda ns:find(ns,'Navigate up') is not None)
    field=next((n for n in ns if n.get('class')=='android.widget.EditText'),None);tap(device,field)
    foreground(device);device.adb('shell','input','keyevent','KEYCODE_MOVE_END',*(['KEYCODE_DEL']*100));device.adb('shell','input','text',input_text_arg(unit))
    ns=wait(device,lambda ns:any(n.get('text')==unit and n.get('class')=='android.widget.TextView' for n in ns))
    tap(device,next(n for n in ns if n.get('text')==unit and n.get('class')=='android.widget.TextView'))
    def selected(ns):
        swap=find(ns,'Swap units')
        if swap is None:return False
        matches=[n for n in ns if n.get('text')==unit and n.get('class')=='android.widget.TextView' and abs(box(n)[1]-box(swap)[1])<25 and ((box(n)[0]<box(swap)[0]) if side=='from_unit' else (box(n)[0]>box(swap)[2]))]
        return len(matches)==1
    wait(device,selected)

def set_units(device,params,context):
    source=str(params['from_unit']);target=str(params['to_unit'])
    if source not in FACTORS or target not in FACTORS:raise ValueError('Unsupported length unit')
    choose_unit(device,source,'from_unit');choose_unit(device,target,'to_unit');state=read_state(device,{},context)
    if (state['from_unit'],state['to_unit'])!=(source,target):raise ValueError('Unit pair did not read back exactly')
    return state

def set_value(device,params,context):
    text=value_param(params['value']);read_state(device,{},context)
    fields=sorted([n for n in nodes(device) if n.get('class')=='android.widget.EditText'],key=lambda n:box(n)[1]);tap(device,fields[0])
    foreground(device);device.adb('shell','input','keyevent','KEYCODE_MOVE_END',*(['KEYCODE_DEL']*100));device.adb('shell','input','text',input_text_arg(text))
    state=read_state(device,{},context)
    if Decimal(state['input_value'])!=Decimal(text):raise ValueError('Entered value did not read back exactly')
    if not result_matches(state):raise ValueError('Displayed conversion differs from standard length definition')
    return state

def swap_units(device,params,context):
    old=read_state(device,{},context);tap(device,find(nodes(device),'Swap units'));state=read_state(device,{},context)
    if (state['from_unit'],state['to_unit'])!=(old['to_unit'],old['from_unit']):raise ValueError('Swap did not exchange the displayed units')
    return state

def clear_value(device,params,context):
    read_state(device,{},context);tap(device,find(nodes(device),'Clear'));state=read_state(device,{},context)
    if Decimal(state['input_value'])!=0 or Decimal(state['output_value'])!=0:raise ValueError('Clear did not reset both values')
    return state

def convert_length(device,params,context):
    value_param(params['value'])
    if params['from_unit'] not in FACTORS or params['to_unit'] not in FACTORS:raise ValueError('Unsupported length unit')
    open_converter(device,{},context);set_units(device,params,context);return set_value(device,params,context)

def result_matches(state):
    try:
        expected=Decimal(state['input_value'])*FACTORS[state['from_unit']]/FACTORS[state['to_unit']]
        # UI default uses three decimals, round-to-nearest. Preserve its rounded display, not a synthesized output.
        return abs(Decimal(state['output_value'])-expected)<=Decimal('.0005001')
    except (KeyError,InvalidOperation):return False

def state_ok(device,context):
    try:
        state=read_state(device,{},context)
        return state==context.result and result_matches(state) and all(state[k]==context.params[k] for k in ['from_unit','to_unit'] if k in context.params) and ('value' not in context.params or Decimal(state['input_value'])==Decimal(context.params['value']))
    except (ValueError,InvalidOperation,ET.ParseError):return False
