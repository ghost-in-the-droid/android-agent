"""Bounded, offline thermocouple reference reads; no wiring or device control."""
from __future__ import annotations
import re,time,html
from gitd.skills.engine.nodes import parse,centre
PKG='com.southerntemp.thermocouples';ID=PKG+':id/'
HOME='com.sec.android.app.launcher';TYPES=('B','E','J','K','N')
def foreground(d):
    if d.foreground_package()!=PKG:raise ValueError('Expected Thermocouples foreground')
def nodes(d):
    foreground(d);ns=[n for n in parse(d.dump_xml(use_portal=False)) if n['package']==PKG]
    for n in ns:n['text']=html.unescape(n['text']);n['desc']=html.unescape(n['desc'])
    return ns
def field(ns,rid):
    matches=[n['text'] for n in ns if n['id']==ID+rid and n['text']]
    if len(matches)!=1:raise ValueError('Expected unique native reference field:'+rid)
    return matches[0]
def record_ok(row):
    return (isinstance(row,dict) and row.get('type') in TYPES and
            isinstance(row.get('positive_metal'),str) and bool(row['positive_metal']) and
            isinstance(row.get('negative_metal'),str) and bool(row['negative_metal']) and
            isinstance(row.get('min_c'),int) and isinstance(row.get('max_c'),int) and
            row['min_c']<row['max_c'] and
            row.get('printed_range_c')==str(row['min_c'])+' to '+str(row['max_c'])+'°C')
def details(ns):
    if not any(n['id']==ID+'DetailsItem' for n in ns):raise ValueError('Expected owned Details navigation')
    title=field(ns,'tcTitle')
    if title not in {'Type '+t for t in TYPES}:raise ValueError('Selected type is outside supported exposed tabs')
    printed=field(ns,'tcTempRange');m=re.fullmatch(r'(-?\d+) to (-?\d+)°C',printed)
    if not m:raise ValueError('Malformed native Celsius range')
    row=dict(type=title.removeprefix('Type '),positive_metal=field(ns,'tcPositiveLeg'),negative_metal=field(ns,'tcNegativeLeg'),printed_range_c=printed,min_c=int(m[1]),max_c=int(m[2]))
    if not record_ok(row):raise ValueError('Invalid native reference record')
    return row
def wait(d,predicate,timeout=15):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(d)
        try:
            if predicate(ns):return ns
        except ValueError:pass
        time.sleep(.15)
    raise ValueError('Expected native thermocouple reference state missing')
def open_app(d,params,c):
    if d.foreground_package() not in {PKG,HOME}:raise ValueError('Refuse entry from unrelated foreground')
    d.adb('shell','am','start','-W','-S','-n',PKG+'/.MainActivity')
    return details(wait(d,lambda ns:bool(details(ns))))
def main_nodes(d):
    if d.foreground_package()==HOME:open_app(d,{},None)
    return nodes(d)
def read_details(d,params,c):return details(main_nodes(d))
def tab(ns,type_name):
    matches=[n for n in ns if n['desc']=='Type '+type_name and n['cls']=='android.widget.LinearLayout' and n['bounds'][2]-n['bounds'][0]>=180]
    if len(matches)!=1:raise ValueError('Expected fully exposed supported type tab')
    return matches[0]
def select_type(d,params,c):
    wanted=params.get('type')
    if wanted not in TYPES:raise ValueError('Use a supported type B/E/J/K/N')
    ns=main_nodes(d);before=details(ns)
    if before['type']!=wanted:
        target=tab(ns,wanted);foreground(d);d.tap(*centre(target),delay=.2)
    return details(wait(d,lambda ns:details(ns)['type']==wanted))
def list_types(d,params,c):
    ns=main_nodes(d);row=details(ns);visible=[]
    for wanted in TYPES:
        try:tab(ns,wanted);visible.append(wanted)
        except ValueError:pass
    if len(visible)<2 or row['type'] not in visible:raise ValueError('Expected supported native type strip')
    return dict(types=visible,current_type=row['type'])
def compare_types(d,params,c):
    left,right=params.get('left'),params.get('right')
    if left not in TYPES or right not in TYPES or left==right:raise ValueError('Choose two distinct supported types')
    first=select_type(d,{'type':left},c);second=select_type(d,{'type':right},c)
    return dict(left=first,right=second,final_type=right)
def details_ok(d,c):
    try:return c.result==details(nodes(d))
    except ValueError:return False
def types_ok(d,c):
    try:return c.result==list_types(d,{},c)
    except ValueError:return False
def comparison_ok(d,c):
    try:
        return (record_ok(c.result.get('left')) and record_ok(c.result.get('right')) and
                c.result['left']['type']==c.params.get('left') and
                c.result['right']['type']==c.params.get('right') and
                c.result['left']['type']!=c.result['right']['type'] and
                c.result['final_type']==c.params.get('right') and c.result['right']==details(nodes(d)))
    except (ValueError,KeyError,TypeError):return False
