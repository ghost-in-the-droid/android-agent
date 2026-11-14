"""Public English dictionary lookup; no history, favourites, audio or sharing."""
import re
import time
import xml.etree.ElementTree as ET
from gitd.bots.common.adb import input_text_arg
PKG='io.github.yamin8000.owl'

def foreground(device):
    if PKG+'/' not in device.adb('shell','dumpsys window | grep -m1 mCurrentFocus'):raise ValueError('Dictionary does not own the focused window')

def nodes(device):
    foreground(device);root=ET.fromstring(device.dump_xml(use_portal=False));foreground(device)
    result=[]
    for n in root.iter('node'):
        v=list(map(int,re.findall(r'\d+',n.get('bounds',''))))
        if n.get('package')==PKG and n.get('enabled')!='false' and len(v)==4 and 0<=v[0]<v[2]<=1080 and 0<=v[1]<v[3]<=2205:result.append(dict(n.attrib))
    return result

def b(n):return list(map(int,re.findall(r'\d+',n['bounds'])))
def field(ns):return next((n for n in ns if n.get('class')=='android.widget.EditText'),None)
def desc(ns,value):return next((n for n in ns if n.get('content-desc')==value),None)
def search_screen(ns):return bool(field(ns) and desc(ns,'Search') and any(n.get('text')=='freeDictionary' for n in ns))
def tap(device,n):
    if not n:raise ValueError('Expected dictionary control is absent')
    foreground(device);v=b(n);device.tap((v[0]+v[2])//2,(v[1]+v[3])//2)

def wait(device,predicate,timeout=25):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(device)
        if predicate(ns):return ns
        time.sleep(.4)
    raise ValueError('Dictionary data unavailable or UI changed')

def term(value):
    value=str(value).lower()
    if not re.fullmatch(r'[a-z]{2,35}',value):raise ValueError('Use one English word, 2 to 35 ASCII letters')
    return value

def values(ns,label):
    keys=[n for n in ns if n.get('text')==label and b(n)[0]<300]
    result=[]
    for key in keys:
        candidates=[n for n in ns if n.get('class')=='android.widget.TextView' and n.get('text') and b(n)[0]>300 and b(n)[3]<1980 and abs((b(n)[1]+b(n)[3]-b(key)[1]-b(key)[3])/2)<100]
        if candidates:
            n=min(candidates,key=lambda n:abs((b(n)[1]+b(n)[3]-b(key)[1]-b(key)[3])/2))
            if n['text'] not in result:result.append(n['text'])
    return result

def entry(ns):
    edit=field(ns)
    if not edit or not edit.get('text'):return None
    word=edit['text'].lower()
    title=next((n for n in ns if n.get('class')=='android.widget.TextView' and n.get('text','').lower()==word and 250<b(n)[1]<600),None)
    definitions=values(ns,'Definition');types=values(ns,'Type')
    if not title or not definitions or not types:return None
    return {'word':title['text'],'parts_of_speech':types,'definitions':definitions,'scope':'Complete visible native definition rows only, not every sense or a full dictionary export. Public dictionary content is untrusted data.'}

def query_state(device,params,context):
    ns=nodes(device);edit=field(ns)
    if not search_screen(ns):raise ValueError('Dictionary search controls are missing')
    return {'screen':'search','query':edit.get('text','')}

def clear_query(device,params,context):
    ns=nodes(device);edit=field(ns)
    if not search_screen(ns):raise ValueError('Main dictionary search screen is required before clearing')
    if edit.get('text'):
        tap(device,desc(ns,'Clear'));ns=wait(device,lambda ns:field(ns) and not field(ns).get('text'))
    return {'screen':'search','query':field(ns).get('text','')}

def open_app(device,params,context):
    device.adb('shell','am','start','-W','-S','-n',PKG+'/.ui.MainActivity');ns=wait(device,search_screen)
    if field(ns).get('text'):
        tap(device,desc(ns,'Clear'));ns=wait(device,lambda ns:field(ns) and not field(ns).get('text'))
    return {'screen':'search','query':field(ns).get('text','')}

def search_word(device,params,context):
    word=term(params['word']);open_app(device,{},context)
    ns=nodes(device);tap(device,field(ns));foreground(device)
    device.adb('shell','input','text',input_text_arg(word));foreground(device);device.press_enter()
    ns=wait(device,lambda ns:entry(ns) is not None and entry(ns)['word'].lower()==word,40)
    return entry(ns)

def read_entry(device,params,context):
    result=entry(nodes(device))
    if not result:raise ValueError('A matching submitted word title, type and complete visible definitions are required')
    return result

def search_ok(device,context):
    try:return context.result==query_state(device,{},context) and context.result.get('query')==''
    except ValueError:return False

def entry_ok(device,context):
    try:
        r=read_entry(device,{},context)
        return r==context.result and (not context.params.get('word') or r['word'].lower()==term(context.params['word']))
    except ValueError:return False
