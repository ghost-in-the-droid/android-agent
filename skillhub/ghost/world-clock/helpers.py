"""Offline Zham city clocks and current-time snapshots; never Android Clock/alarms."""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re
import time
import xml.etree.ElementTree as ET
from gitd.bots.common.adb import input_text_arg
PKG='io.github.haykh.zham'

def foreground(device):
    raw=device.adb('shell','dumpsys window');line=next((l for l in raw.splitlines() if 'mCurrentFocus=' in l),'')
    if PKG+'/' in line:return
    token=re.search(r'Window\{([a-f0-9]+)\b',line)
    if token:
        for block in re.split(r'(?=  Window #)',raw):
            if re.match(r'  Window #\d+ Window\{'+token[1]+r'\b',block) and re.search(r'\bpackage='+re.escape(PKG)+r'(?:\s|[},])',block) and re.search(r'\bmOwnerUid=\d+',block):return
    raise ValueError('Zham does not own the focused window')

def nodes(device):
    # Portal reads live clocks without waiting for uiautomator idle; ownership is
    # independently checked against the native focused window before AND after.
    foreground(device);xml=device.dump_xml();foreground(device)
    return [dict(n.attrib) for n in ET.fromstring(xml).iter('node') if n.get('enabled')!='false' and n.get('package',PKG)==PKG and n.get('bounds')!='[0,0][0,0]']

def b(n):return list(map(int,re.findall(r'\d+',n['bounds'])))
def find(ns,text):return next((n for n in ns if n.get('text')==text),None)
def tap(device,n):
    if not n:raise ValueError('Expected Zham control is absent')
    foreground(device);v=b(n);device.tap((v[0]+v[2])//2,(v[1]+v[3])//2)

def wait(device,predicate,timeout=15):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(device)
        if predicate(ns):return ns
        time.sleep(.25)
    raise ValueError('Zham view unavailable or controls changed')

def zone(value):
    value=str(value)
    if not re.fullmatch(r'[A-Za-z_]+(?:/[A-Za-z0-9_+\-]+){1,2}',value):raise ValueError('Use an Area/City IANA time-zone identifier')
    try:ZoneInfo(value)
    except ZoneInfoNotFoundError:raise ValueError('Unknown IANA time zone') from None
    return value

def clock_mode(ns):return bool(find(ns,'World Clock') and find(ns,'Clocks') and not find(ns,'Search zones'))
def converter(ns):return bool(any(n.get('text')=='Convert' and b(n)[1]<200 for n in ns) and find(ns,'Now') and not find(ns,'World Clock'))
def rows(ns):
    result=[]
    for n in ns:
        value=n.get('text','')
        if not re.fullmatch(r'[A-Za-z_]+(?:/[A-Za-z0-9_+\-]+){1,2}',value):continue
        z=b(n)
        if z[3]>2205:continue
        times=[m for m in ns if re.fullmatch(r'\d\d:\d\d:\d\d',m.get('text','')) and b(m)[0]>z[0]+300 and abs((b(m)[1]+b(m)[3]-z[1]-z[3])/2)<100 and b(m)[3]<=2205]
        names=[m for m in ns if m.get('text','').isascii() and m.get('text','').strip() and b(m)[1]<z[1] and 0<=z[1]-b(m)[3]<35 and abs(b(m)[0]-z[0])<150]
        if len(times)==1 and names:result.append({'city':max(names,key=lambda m:b(m)[1])['text'],'zone':value,'time':times[0]['text']})
    return result

def read_clocks(device,params,context):
    ns=nodes(device);r=rows(ns)
    if not clock_mode(ns) or not r:raise ValueError('Readable Zham city clocks are required')
    return {'screen':'clocks','clocks':r,'scope':'Complete currently visible city rows only. Times are snapshots, not the phone location.'}

def open_app(device,params,context):
    device.adb('shell','am','start','-W','-S','-n',PKG+'/.MainActivity')
    ns=wait(device,lambda ns:find(ns,'Clocks'))
    if not clock_mode(ns):tap(device,next(n for n in ns if n.get('text')=='Clocks' and b(n)[1]>2000))
    wait(device,clock_mode);return read_clocks(device,params,context)

def add_city(device,params,context):
    target=zone(params['zone']);ns=nodes(device)
    if not clock_mode(ns):raise ValueError('Open the city clocks first')
    if target in [r['zone'] for r in rows(ns)]:return read_clocks(device,params,context)
    tap(device,find(ns,'Add city'));ns=wait(device,lambda ns:find(ns,'Search zones'))
    edit=next((n for n in ns if n.get('class')=='android.widget.EditText' and not n.get('text')),None);tap(device,edit)
    foreground(device);device.adb('shell','input','text',input_text_arg(target))
    ns=wait(device,lambda ns:any(n.get('text')==target and n.get('class')=='android.widget.TextView' for n in ns) and any(n.get('text')==target and n.get('class')=='android.widget.EditText' for n in ns))
    tap(device,next(n for n in ns if n.get('text')==target and n.get('class')=='android.widget.TextView'))
    wait(device,lambda ns:clock_mode(ns) and target in [r['zone'] for r in rows(ns)])
    return read_clocks(device,params,context)

def open_converter(device,params,context):
    ns=nodes(device)
    if not clock_mode(ns):raise ValueError('Open the city clocks first')
    tap(device,next(n for n in ns if n.get('text')=='Convert' and b(n)[1]>2000));wait(device,converter)
    return read_conversion(device,params,context)

def read_conversion(device,params,context):
    ns=nodes(device);r=rows(ns)
    if not converter(ns) or not r:raise ValueError('Readable conversion snapshot is required')
    reference=next((n['text'] for n in ns if n.get('class')=='android.widget.TextView' and b(n)[1]>180 and b(n)[3]<300),'')
    date=next((n['text'] for n in ns if re.fullmatch(r'[A-Z][a-z]{2}, [A-Z][a-z]{2} \d{1,2}',n.get('text',''))),'')
    if not reference or not date:raise ValueError('Conversion reference city/date is missing')
    return {'screen':'conversion','reference_city':reference,'reference_date':date,'clocks':r,'scope':'App snapshot for its current selected instant; date is for the reference city. Other cities can be on different dates. No alarm or device clock change.'}

def reset_now(device,params,context):
    ns=nodes(device)
    if not converter(ns):raise ValueError('Open the converter first')
    candidates=[n for n in ns if n.get('text')=='Now'];tap(device,max(candidates,key=lambda n:b(n)[1]))
    wait(device,converter);return read_conversion(device,params,context)

def back_to_clocks(device,params,context):
    ns=nodes(device)
    if not converter(ns):raise ValueError('Clocks navigation is restricted to the converter view')
    tap(device,next(n for n in ns if n.get('text')=='Clocks' and b(n)[1]>2000));wait(device,clock_mode)
    return read_clocks(device,params,context)

def seconds(text):
    h,m,s=map(int,text.split(':'))
    if not (0<=h<24 and 0<=m<60 and 0<=s<60):raise ValueError('Invalid clock time')
    return h*3600+m*60+s

def clocks_ok(device,context):
    r=context.result;ns=nodes(device)
    if r.get('screen')!='clocks' or not r.get('clocks') or not clock_mode(ns):return False
    fresh={x['zone']:x for x in rows(ns)};epoch=int(device.adb('shell','date','+%s'))
    if context.params.get('zone') and context.params['zone'] not in fresh:return False
    for row in r['clocks']:
        if row['zone'] not in fresh or fresh[row['zone']]['city']!=row['city']:return False
        expected=datetime.fromtimestamp(epoch,ZoneInfo(row['zone'])).strftime('%H:%M:%S');delta=abs(seconds(row['time'])-seconds(expected))
        if min(delta,86400-delta)>20:return False
    return True

def conversion_ok(device,context):
    try:return context.result==read_conversion(device,{},context)
    except ValueError:return False
