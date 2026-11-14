"""Bundled Berlin/Hamburg solar table only, never device location or alarms."""
import re,time,datetime,xml.etree.ElementTree as ET
from gitd.bots.common.adb import input_text_arg
PKG='com.forrestguice.suntimeswidget'
CITIES={'Berlin','Hamburg'}
def foreground(d):
    text=d.adb('shell','dumpsys','window');line=next((l for l in text.splitlines() if 'mCurrentFocus=' in l),'')
    if PKG+'/' in line:return
    token=re.search(r'Window\{([a-f0-9]+)\b',line)
    if token:
        for block in re.split(r'(?=  Window #)',text):
            if re.match(r'  Window #\d+ Window\{'+token[1]+r'\b',block) and re.search(r'\bpackage='+re.escape(PKG)+r'(?:\s|[},])',block) and re.search(r'\bmOwnerUid=\d+',block):return
    raise ValueError('Suntimes must own the exact native focused window')
def protected(d):
    for op in ['FINE_LOCATION','COARSE_LOCATION']:
        if not re.search(r'\bignore\b',d.adb('shell','appops','get',PKG,op)):raise ValueError('Location app-ops must be denied')
def bounds(n):return list(map(int,re.findall(r'\d+',n.get('bounds',''))))
def nodes(d):
    protected(d);foreground(d);root=ET.fromstring(d.dump_xml(use_portal=False));foreground(d)
    return [dict(n.attrib) for n in root.iter('node') if n.get('package')==PKG and len(bounds(n))==4 and 0<=bounds(n)[0]<bounds(n)[2]<=1080 and 0<=bounds(n)[1]<bounds(n)[3]<=2205 and n.get('enabled')!='false']
def find(ns,text=None,desc=None,rid=None):
    return next((n for n in ns if (text is None or n.get('text')==text) and (desc is None or n.get('content-desc')==desc) and (rid is None or n.get('resource-id')==(rid if ':' in rid else PKG+':id/'+rid))),None)
def value(ns,rid):
    n=find(ns,rid=rid);return n.get('text','') if n else None
def tap(d,n):
    if n is None:raise ValueError('Expected safe native control missing')
    protected(d);foreground(d);v=bounds(n);d.tap((v[0]+v[2])//2,(v[1]+v[3])//2)
def wait(d,pred,timeout=35):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(d)
        if pred(ns):return ns
        time.sleep(.3)
    raise ValueError('Expected native Suntimes state unavailable')
def city(p):
    c=p.get('city')
    if c not in CITIES:raise ValueError('Only bundled Berlin/Hamburg are supported')
    return c
def state(ns):
    if not find(ns,rid='action_location_add') or find(ns,rid='dialog_title'):raise ValueError('Main sun/moon table required')
    names=[n['text'] for n in ns if n.get('class')=='android.widget.TextView' and n.get('text') in CITIES and bounds(n)[1]<180]
    date=value(ns,'text_date') or '';match=re.search(r'([A-Za-z]{3} \d{1,2}, \d{4})',date)
    zone=value(ns,'text_timezone') or ''
    if len(names)!=1 or not match or not zone.startswith('Europe/Berlin'):raise ValueError('Supported named city/date/time zone required')
    fields={k:value(ns,r) for k,r in [('sunrise','text_time_sunrise_actual'),('sunset','text_time_sunset_actual'),('day_length','text_daylength'),('moon_phase','text_info_moonphase'),('moonrise','text_time_moonrise'),('moonset','text_time_moonset'),('moon_illumination','text_info_moonillum')]}
    if not all(fields[k] for k in ['sunrise','sunset','day_length','moon_phase']):raise ValueError('Native sun/moon values missing')
    return dict(city=names[0],date=datetime.datetime.strptime(match[1],'%b %d, %Y').date().isoformat(),displayed_date=date,time_zone=zone,**fields,scope='App-calculated public city table; GPS denied, no independent astronomical verification')
def ready(ns):
    try:state(ns);return True
    except ValueError:return False
def prepare(d):
    for op in ['FINE_LOCATION','COARSE_LOCATION']:d.adb('shell','appops','set',PKG,op,'ignore')
    for perm in ['POST_NOTIFICATIONS','ACCESS_FINE_LOCATION','ACCESS_COARSE_LOCATION']:
        d.adb('shell','pm','revoke',PKG,'android.permission.'+perm)
        d.adb('shell','pm','set-permission-flags',PKG,'android.permission.'+perm,'user-set','user-fixed')
    protected(d)
def open_app(d,p,c):
    prepare(d);d.adb('shell','am','start','-W','-n',PKG+'/.SuntimesLaunchActivity')
    for _ in range(30):
        try:foreground(d);break
        except ValueError:time.sleep(.1)
    else:raise ValueError('Suntimes did not acquire focus')
    for _ in range(10):
        ns=nodes(d)
        if ready(ns):return state(ns)
        if find(ns,rid='button_build_places'):
            tap(d,find(ns,rid='button_build_places'));ns=wait(d,lambda ns:find(ns,text='Europe') and find(ns,text='ADD'))
            europe=find(ns,text='Europe')
            if europe.get('checked')!='true':tap(d,europe)
            tap(d,find(nodes(d),text='ADD'))
            ns=wait(d,lambda ns:find(ns,text='Berlin',rid='android:id/text1'))
            tap(d,find(ns,text='Berlin',rid='android:id/text1'));ns=wait(d,lambda ns:find(ns,rid='button_next'))
        n=find(ns,rid='button_next')
        if not n or n.get('text') not in {'NEXT','FINISH'}:raise ValueError('Unexpected onboarding; no permission/settings bypass')
        tap(d,n)
    raise ValueError('Onboarding did not reach supported Berlin table')
def read_state(d,p,c):return state(nodes(d))
def searched(ns,wanted):
    if value(ns,'search_src_text')!=wanted or not find(ns,text=wanted,rid='android:id/text1') or find(ns,rid='pickPlace'):raise ValueError('Exact public city search result required')
    return dict(city=wanted,query=wanted,scope='Bundled European Places search; no GPS')
def search_city(d,p,c):
    wanted=city(p);ns=nodes(d);state(ns);tap(d,find(ns,rid='action_location_add'))
    ns=wait(d,lambda ns:find(ns,text='User Defined') and find(ns,rid='appwidget_location_list'))
    tap(d,find(ns,rid='appwidget_location_list'));ns=wait(d,lambda ns:find(ns,desc='Search'))
    tap(d,find(ns,desc='Search'));ns=wait(d,lambda ns:find(ns,rid='search_src_text'))
    foreground(d);d.adb('shell','input','text',input_text_arg(wanted))
    ns=wait(d,lambda ns:value(ns,'search_src_text')==wanted and find(ns,text=wanted,rid='android:id/text1'))
    return searched(ns,wanted)
def select_city(d,p,c):
    wanted=city(p);ns=nodes(d);searched(ns,wanted);tap(d,find(ns,text=wanted,rid='android:id/text1'))
    ns=wait(d,lambda ns:find(ns,rid='pickPlace') and value(ns,'action_bar_title')==wanted)
    tap(d,find(ns,rid='pickPlace'));ns=wait(d,lambda ns:find(ns,text='User Defined') and find(ns,text=wanted,rid='android:id/text1') and find(ns,desc='Update'))
    tap(d,find(ns,desc='Update'));ns=wait(d,lambda ns:ready(ns) and state(ns)['city']==wanted)
    return state(ns)
def next_day(d,p,c):
    ns=nodes(d);before=state(ns);tap(d,find(ns,rid='text_date'));expected=(datetime.date.fromisoformat(before['date'])+datetime.timedelta(days=1)).isoformat()
    return state(wait(d,lambda ns:ready(ns) and state(ns)['date']==expected and state(ns)['city']==before['city']))
def state_ok(d,c):
    try:return c.result==read_state(d,{},c)
    except ValueError:return False
def search_ok(d,c):
    try:return c.result==searched(nodes(d),c.result['city'])
    except (ValueError,KeyError):return False
