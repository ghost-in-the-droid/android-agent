"""Offline Birdipedia name catalog only; never tap a bird/external link."""
from __future__ import annotations
import re,time,html,xml.etree.ElementTree as ET
from gitd.bots.common.adb import input_text_arg
from gitd.skills.engine.nodes import parse,centre
PKG='de.katzenmue.birdipedia'
HOME='com.sec.android.app.launcher'
def foreground(d):
    if d.foreground_package()!=PKG:raise ValueError('Expected Birdipedia foreground')
def nodes(d):
    foreground(d)
    ns=[n for n in parse(d.dump_xml(use_portal=False)) if n['package']==PKG]
    for n in ns:
        n['text']=html.unescape(n['text']);n['desc']=html.unescape(n['desc'])
    return ns
def tap(d,n):
    foreground(d);d.tap(*centre(n),delay=.2)
def edit(ns):
    es=[n for n in ns if n['cls']=='android.widget.EditText']
    if len(es)!=1 or not any(n['desc']=='Menu' for n in ns) or not any(n['text']=='Filter by Name' for n in ns):raise ValueError('Expected owned filter toolbar')
    return es[0]
def state(ns):
    e=edit(ns);views=[n for n in ns if n['cls']=='android.widget.TextView' and n['text'] and n['bounds'][1]>e['bounds'][3]]
    pairs=[]
    for scientific in sorted(views,key=lambda n:n['bounds'][1]):
        if not re.fullmatch(r'[A-Z][a-z]+ [a-z][a-z-]+(?: [a-z][a-z-]+)?',scientific['text']):continue
        b=scientific['bounds']
        if b[3]-b[1]<50:continue
        names=[n for n in views if n['bounds'][0]==b[0] and 0<b[1]-n['bounds'][3]<=40 and n['bounds'][3]-n['bounds'][1]>=50]
        if len(names)!=1:continue
        pairs.append(dict(common_name=names[0]['text'],scientific_name=scientific['text']))
    if len(pairs)<2:raise ValueError('Two complete native bird name pairs required')
    groups=[n['text'] for n in views if n['bounds'][0]<100 and re.fullmatch(r'[A-Z][a-z]+',n['text'])]
    query=e['text']
    if query and not all(query.casefold() in row['common_name'].casefold() or query.casefold() in row['scientific_name'].casefold() for row in pairs[:2]):raise ValueError('Native rows do not match the exposed query')
    return dict(query=query,birds=pairs[:2],taxonomic_groups=groups)
def wait(d,predicate,timeout=20):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(d)
        try:
            if predicate(ns):return ns
        except ValueError:pass
        time.sleep(.2)
    raise ValueError('Expected native bird catalog state missing')
def ready(ns):
    try:state(ns);return True
    except ValueError:return False
def open_app(d,p,c):
    if d.foreground_package() not in {PKG,HOME}:raise ValueError('Refuse entry from unrelated foreground')
    d.adb('shell','am','start','-W','-S','-n',PKG+'/.MainActivity')
    return state(wait(d,lambda ns:ready(ns) and state(ns)['query']==''))
def main_nodes(d):
    if d.foreground_package()==HOME:open_app(d,{},None)
    return nodes(d)
def read_results(d,p,c):return state(main_nodes(d))
def hide_keyboard(d):
    foreground(d)
    status=d.adb('shell', "dumpsys input_method | grep -E 'mInputShown|mIsInputViewShown'")
    if re.search(r'(?:mInputShown|mIsInputViewShown)=true',status):
        foreground(d);d.back(delay=.2);foreground(d)
def set_query(d,query):
    ns=main_nodes(d);state(ns);tap(d,edit(ns))
    foreground(d);d.adb('shell','input','keycombination','KEYCODE_CTRL_LEFT','KEYCODE_A')
    foreground(d);d.adb('shell','input','keyevent','KEYCODE_DEL')
    if query:
        foreground(d);d.adb('shell','input','text',input_text_arg(query))
    wait(d,lambda ns:ready(ns) and state(ns)['query']==query)
    hide_keyboard(d)
    return state(wait(d,lambda ns:ready(ns) and state(ns)['query']==query))
def filter_birds(d,p,c):
    query=p.get('query')
    if not isinstance(query,str) or not re.fullmatch(r'[A-Za-z][A-Za-z -]{0,39}',query):raise ValueError('Use1–40 ASCII name letters/spaces/hyphens')
    return set_query(d,query)
def clear_filter(d,p,c):return set_query(d,'')
def scroll_results(d,p,c):
    ns=main_nodes(d);before=state(ns)
    science=[n for n in ns if n['text'] in {r['scientific_name'] for r in before['birds']}]
    top=min(n['bounds'][1] for n in science)
    bottom=max(n['bounds'][3] for n in ns if n['cls']=='android.widget.TextView' and n['bounds'][0]>300)
    if bottom-top<500:raise ValueError('Not enough native list area for a safe scroll')
    foreground(d);d.swipe(540,bottom-30,540,top+30,350,delay=.2)
    return state(wait(d,lambda ns:ready(ns) and state(ns)['birds']!=before['birds']))
def state_ok(d,c):
    try:return c.result==state(nodes(d))
    except ValueError:return False
