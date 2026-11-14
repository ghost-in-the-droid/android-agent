"""VBB public station lookup; location denied and no ticket or location actions."""
import re
import time
import xml.etree.ElementTree as ET
from gitd.bots.common.adb import input_text_arg
PKG='de.grobox.liberario'

def foreground(device):
    text=device.adb('shell','dumpsys','window');line=next((l for l in text.splitlines() if 'mCurrentFocus=' in l),'')
    match=re.search(r'\s([A-Za-z][\w.]*)/[^\s}]+',line)
    if match and match.group(1)==PKG:return
    token=re.search(r'Window\{([a-f0-9]+)\b',line)
    if token and not match:
        for block in re.split(r'(?=  Window #)',text):
            if re.match(r'  Window #\d+ Window\{'+token.group(1)+r'\b',block) and re.search(r'\bpackage='+re.escape(PKG)+r'(?:\s|[},])',block) and re.search(r'\bmOwnerUid=\d+',block):return
    raise ValueError('Transportr must own the focused native window')
def bounds(n):return list(map(int,re.findall(r'\d+',n.get('bounds',''))))
def nodes(device):
    foreground(device);root=ET.fromstring(device.dump_xml());foreground(device)
    return [dict(n.attrib) for n in root.iter('node') if len(bounds(n))==4 and 0<=bounds(n)[0]<bounds(n)[2]<=1080 and 0<=bounds(n)[1]<bounds(n)[3]<=2205 and n.get('enabled')!='false']
def find(ns,text=None,id=None,desc=None):return next((n for n in ns if (text is None or n.get('text')==text) and (id is None or n.get('resource-id')==PKG+':id/'+id) and (desc is None or n.get('content-desc')==desc)),None)
def tap(device,n):
    if n is None:raise ValueError('Expected public transit control is missing')
    foreground(device);v=bounds(n);device.tap((v[0]+v[2])//2,(v[1]+v[3])//2)
def wait(device,predicate,timeout=35):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(device)
        if predicate(ns):return ns
        time.sleep(.4)
    raise ValueError('Transit provider unavailable or expected station/result absent')

def stable_read(device,reader,timeout=12):
    """Require two equal owned-window reads before returning live provider data."""
    deadline=time.monotonic()+timeout;previous=None
    while time.monotonic()<deadline:
        ns=nodes(device)  # Ownership failures propagate; no input or foreign-window retry.
        try:value=reader(ns)
        except ValueError:previous=None
        else:
            if previous is not None and value==previous:return value
            previous=value
        time.sleep(.3)
    raise ValueError('Public transit rows did not stabilize before the deadline')

def text_param(value):
    value=str(value).strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 +().,-]{1,79}',value):raise ValueError('Use a 2–80 character public station name/query')
    return value

def map_search(ns):return find(ns,id='map') is not None and find(ns,id='location') is not None and find(ns,id='material_drawer_name') is None

def open_app(device,params,context):
    for permission in ['ACCESS_FINE_LOCATION','ACCESS_COARSE_LOCATION']:
        device.adb('shell','pm','revoke',PKG,'android.permission.'+permission)
        device.adb('shell','pm','set-permission-flags',PKG,'android.permission.'+permission,'user-set','user-fixed')
    device.adb('shell','am','start','-W','-S','-n',PKG+'/de.grobox.transportr.map.MapActivity')
    # am start -W may finish before Samsung assigns the focused surface.
    # Poll ownership only; no input while the focused window is unknown/foreign.
    for _ in range(30):
        try:foreground(device);break
        except ValueError:time.sleep(.1)
    else:raise ValueError('Transportr did not acquire native focus after launch')
    ns=nodes(device)
    if find(ns,text='Choose Area'):
        for name in ['Europe','Germany','VBB']:
            tap(device,find(ns,text=name));ns=wait(device,lambda ns:find(ns,text='Germany') is not None if name=='Europe' else find(ns,text='VBB') is not None if name=='Germany' else map_search(ns))
    if not map_search(ns):raise ValueError('Expected VBB fresh map/search screen')
    # Network drawer contains only the public provider label; close by a guarded
    # drawer swipe, never Back (Back can exit this activity on Samsung).
    tap(device,find(ns,id='menu'));ns=wait(device,lambda ns:find(ns,id='material_drawer_account_header_name') is not None)
    if find(ns,id='material_drawer_account_header_name').get('text')!='VBB':raise ValueError('Only VBB is supported')
    foreground(device);device.swipe(850,1100,20,1100,300);wait(device,map_search)
    return {'screen':'station_search','network':'VBB','location_permission':'denied'}

def choose(device,n,query,expected):
    query=text_param(query);expected=text_param(expected)
    if not n or n.get('text') not in {'Search here','To','From',''}:raise ValueError('An empty station input is required')
    tap(device,n);foreground(device);device.adb('shell','input','text',input_text_arg(query));time.sleep(3)
    foreground(device);device.adb('shell','input','keyevent','KEYCODE_DPAD_DOWN');foreground(device);device.press_enter()
    return wait(device,lambda ns:any(n.get('resource-id')==PKG+':id/location' and n.get('text')==expected for n in ns))

def station(ns):
    name=find(ns,id='locationName');box=find(ns,id='location')
    if not name or not box or name.get('text')!=box.get('text') or find(ns,id='departuresButton') is None:raise ValueError('An explicitly selected station overview is required')
    return {'station':name['text'],'network':'VBB','scope':'Public named station only; coordinates omitted.'}
def dismiss_hint(device,ns):
    if find(ns,id='material_target_prompt_view'):
        foreground(device);device.back();ns=wait(device,lambda ns:find(ns,id='material_target_prompt_view') is None)
    return ns

def search_station(device,params,context):
    ns=nodes(device)
    if not map_search(ns) or find(ns,id='location').get('text')!='Search here':open_app(device,{},context);ns=nodes(device)
    ns=choose(device,find(ns,id='location'),params['query'],params['station']);ns=wait(device,lambda ns:find(ns,id='locationName') is not None);ns=dismiss_hint(device,ns)
    result=station(ns)
    if result['station']!=params['station']:raise ValueError('Selected station does not exactly match')
    return result

def rows_by_start(ns,startid,fields):
    starts=sorted([n for n in ns if n.get('resource-id')==PKG+':id/'+startid],key=lambda n:bounds(n)[1]);rows=[]
    for i,start in enumerate(starts):
        low=bounds(start)[1];high=bounds(starts[i+1])[1] if i+1<len(starts) else 2205
        row={};owned=[n for n in ns if low<=bounds(n)[1] and bounds(n)[3]<=high]
        for output,rid in fields.items():
            values=[n.get('text','') for n in owned if n.get('resource-id')==PKG+':id/'+rid and n.get('text')]
            if len(values)!=1:break
            row[output]=values[0]
        else:
            if len(row)==len(fields):rows.append((row,owned))
    return rows

def departures(ns):
    if not find(ns,text='Departures'):raise ValueError('Departures screen required')
    titles=[n['text'] for n in ns if n.get('text') and n.get('class')=='android.widget.TextView' and not n.get('resource-id') and 160<=bounds(n)[1]<238]
    rows=rows_by_start(ns,'departureTimeRel',{'service':'line','destination':'destinationView','departure':'departureTimeAbs'})
    if len(titles)!=1 or len(rows)<3:raise ValueError('Station heading and three complete departure rows required')
    return {'station':titles[0],'network':'VBB','departures':[r for r,_ in rows[:3]],'scope':'Literal public live rows; no operating or journey guarantee.'}
def read_departures(device,params,context):
    ns=nodes(device)
    if not find(ns,text='Departures'):
        station(ns);tap(device,find(ns,id='departuresButton'));ns=wait(device,lambda ns:len(rows_by_start(ns,'departureTimeRel',{'service':'line','destination':'destinationView','departure':'departureTimeAbs'}))>=3)
    return stable_read(device,departures)

def connections(ns):
    fields=[n.get('text') for n in ns if n.get('resource-id')==PKG+':id/location']
    if len(fields)!=2 or any(v in {'From','To','','Search here'} for v in fields):raise ValueError('Two explicitly selected route endpoints required')
    rows=rows_by_start(ns,'fromTimeRel',{'departure':'fromTime','origin':'fromLocation','arrival':'toTime','destination':'toLocation','duration':'duration'})
    result=[]
    for row,owned in rows:
        services=[n['text'] for n in owned if n.get('text') and n.get('class')=='android.widget.TextView' and not n.get('resource-id') and re.fullmatch(r'[A-Z]+\s?\d+[A-Za-z]?',n['text'])]
        if row['origin']==fields[0] and row['destination']==fields[1] and services:result.append({**row,'services':services})
    if len(result)<3:raise ValueError('Three complete route cards matching both endpoints required')
    return {'origin':fields[0],'destination':fields[1],'network':'VBB','connections':result[:3],'scope':'Visible departure-now connection labels; not a booking or service guarantee.'}
def search_connections(device,params,context):
    for key in ['origin_query','origin_station','destination_query','destination_station']:text_param(params[key])
    if params['origin_station']==params['destination_station']:raise ValueError('Use two distinct stations')
    open_app(device,{},context);search_station(device,{'query':params['origin_query'],'station':params['origin_station']},context);ns=nodes(device)
    tap(device,find(ns,id='overflowButton'));ns=wait(device,lambda ns:find(ns,text='From Here') is not None);tap(device,find(ns,text='From Here'))
    ns=wait(device,lambda ns:find(ns,id='location',text='To') is not None)
    ns=choose(device,find(ns,id='location',text='To'),params['destination_query'],params['destination_station'])
    ns=wait(device,lambda ns:len(rows_by_start(ns,'fromTimeRel',{'departure':'fromTime','origin':'fromLocation','arrival':'toTime','destination':'toLocation','duration':'duration'}))>=3)
    result=stable_read(device,connections)
    if result['origin']!=params['origin_station'] or result['destination']!=params['destination_station']:raise ValueError('Route endpoints mismatch')
    return result
def read_connections(device,params,context):return stable_read(device,connections)

def open_ok(device,context):
    try:return context.result.get('network')=='VBB' and context.result.get('location_permission')=='denied' and map_search(nodes(device))
    except ValueError:return False
def station_ok(device,context):
    try:return context.result==station(nodes(device)) and context.result['station']==context.params['station']
    except ValueError:return False
def departures_ok(device,context):
    try:return context.result==departures(nodes(device))
    except ValueError:return False
def connections_ok(device,context):
    try:
        r=connections(nodes(device))
        return r==context.result and (not context.params.get('origin_station') or r['origin']==context.params['origin_station']) and (not context.params.get('destination_station') or r['destination']==context.params['destination_station'])
    except ValueError:return False
