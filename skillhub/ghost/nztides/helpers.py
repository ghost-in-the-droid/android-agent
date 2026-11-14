"""Public bundled tide rows, preserving the printed offset; no GPS."""
import re,time,datetime,xml.etree.ElementTree as ET
PKG='com.palliser.nztides'
PORTS={'Waitangi - Chatham Island', 'Tamaki River', 'Weiti River Entrance', 'Omaha Bridge', 'Town Basin', 'Oamaru', 'Whitianga', 'Fishing Rock - Raoul Island', 'Akaroa', 'Whangārei', 'Port Chalmers', 'Ben Gunn Wharf', 'Scott Base', 'Sumner Head', 'Gisborne', 'Thames', 'Charleston', 'Opua', 'Te Weka Bay', 'Wellington', 'Motuara Island', 'Whanganui River Entrance', 'Kaingaroa - Chatham Island', 'Rangatira Point', 'Manu Bay', 'Māpua', 'Owenga - Chatham Island', 'Timaru', 'Raglan', 'New Brighton Pier', 'Dunedin', 'Westport', 'Lyttelton', 'Tauranga', 'Kaiteriteri', 'Marsden Point', 'Green Island', 'Kaituna River Entrance', 'Elie Bay', 'Elaine Bay', 'Spit Wharf', 'Ōmokoroa', 'Long Island', 'Whakatāne', 'Kaikōura', 'Whangaroa', 'Dargaville', 'Korotiti Bay', 'Havelock', 'Leigh', 'Waihopai River Entrance', 'Mana Marina', 'North Cape - Otou', 'Huruhi Harbour', 'Port Taranaki', 'Anakakata Bay', 'Riverton - Aparima', 'Picton', 'Pouto Point', 'Tarakohe', 'Anawhata', 'Jackson Bay', 'Napier', 'Lottin Point - Wakatiri', 'Auckland', 'Fresh Water Basin', 'Ōpōtiki Wharf', 'Kawhia', 'Ōkukari Bay', 'Bluff', 'Castlepoint', 'Richmond Bay', 'Wilson Bay', 'Halfmoon Bay - Oban', 'Nelson', 'Moturiki Island', 'Deep Cove', 'Helensville', 'Opononi', 'Rangitaiki River Entrance', 'Port Ōhope Wharf', 'Dog Island', 'Welcombe Bay', 'Flour Cask Bay', 'Paratutae Island', "Man o'War Bay", 'Matiatia Bay', 'Onehunga'}
def foreground(d):
    text=d.adb('shell','dumpsys','window');line=next((l for l in text.splitlines() if 'mCurrentFocus=' in l),'')
    if PKG+'/' in line:return
    token=re.search(r'Window\{([a-f0-9]+)\b',line)
    if token:
        for block in re.split(r'(?=  Window #)',text):
            if re.match(r'  Window #\d+ Window\{'+token[1]+r'\b',block) and re.search(r'\bpackage='+re.escape(PKG)+r'(?:\s|[},])',block) and re.search(r'\bmOwnerUid=\d+',block):return
    raise ValueError('NZ Tides must own the exact native focused window')
def bounds(n):return list(map(int,re.findall(r'\d+',n.get('bounds',''))))
def nodes(d):
    foreground(d);root=ET.fromstring(d.dump_xml(use_portal=False));foreground(d)
    return [dict(n.attrib) for n in root.iter('node') if n.get('package')==PKG and len(bounds(n))==4 and 0<=bounds(n)[0]<bounds(n)[2]<=1080 and 0<=bounds(n)[1]<bounds(n)[3]<=2205 and n.get('enabled')!='false']
def find(ns,text=None,desc=None):return next((n for n in ns if (text is None or n.get('text')==text) and (desc is None or n.get('content-desc')==desc)),None)
def tap(d,n):
    if n is None:raise ValueError('Expected public native control missing')
    foreground(d);v=bounds(n);d.tap((v[0]+v[2])//2,(v[1]+v[3])//2)
def wait(d,pred,timeout=30):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(d)
        if pred(ns):return ns
        time.sleep(.3)
    raise ValueError('Native public port/table unavailable')
def table(ns,now=None):
    if not find(ns,text='NZ Tides') or not find(ns,desc='More options') or find(ns,text='Choose Port') or find(ns,text='About'):raise ValueError('Main native tide table required')
    bodies=[n.get('text','') for n in ns if n.get('class')=='android.widget.ScrollView' and n.get('text','').startswith('[')]
    if len(bodies)!=1:raise ValueError('Exact native tide body required')
    body=bodies[0];header=re.match(r'\[([^\]]+)\]\s*([+-]?\d+(?:\.\d+)?)m\s*([↑↓])(\d+(?:\.\d+)?)m/hr',body)
    if not header or header[1] not in PORTS:raise ValueError('Bundled port estimate header missing')
    matches=re.findall(r'^\s*([+-]?\d+\.\d+) ([HL]) (\d{2}:\d{2}) ([A-Za-z]{3}) (\d{2}/\d{2}/\d{2}) (GMT[+-]\d{2}:\d{2})\s*$',body,re.M)[:3]
    if len(matches)!=3:raise ValueError('Three explicit-offset native tide rows required')
    events=[];moments=[]
    for height,kind,clock,weekday,date,zone in matches:
        stamp=datetime.datetime.strptime(date+' '+clock+' '+zone[3:],'%d/%m/%y %H:%M %z')
        if stamp.strftime('%a')!=weekday:raise ValueError('Native tide weekday/date mismatch')
        moments.append(stamp);events.append(dict(height_m=height,kind='high' if kind=='H' else 'low',time=clock,date=stamp.date().isoformat(),printed_date=date,time_zone=zone))
    now=now or datetime.datetime.now(datetime.timezone.utc)
    if not moments[0]<=now<moments[1]<moments[2] or any((b-a).total_seconds()>12*3600 for a,b in zip(moments,moments[1:])) or events[0]['kind']==events[1]['kind'] or events[1]['kind']==events[2]['kind']:raise ValueError('Expired, out-of-order or nonalternating tide data')
    return dict(port=header[1],estimate_height_m=header[2],direction='rising' if header[3]=='↑' else 'falling',rate_m_per_hour=header[4],events=events,scope='Native bundled predictions/estimates, not independent verification. Printed phone time zone is preserved, not converted to port local time. Not for navigation.')
def ready(ns):
    try:table(ns);return True
    except ValueError:return False
def ports(ns):
    if not find(ns,text='Choose Port') or not find(ns,text='Cancel'):raise ValueError('Open native Choose Port dialog required')
    names=[n['text'] for n in ns if n.get('class')=='android.widget.TextView' and n.get('text') in PORTS and 250<=bounds(n)[1] and bounds(n)[3]<=1980]
    if not names:raise ValueError('No exposed bundled port rows')
    return dict(ports=names,scope='Exposed bundled public names only; scroll to reveal more')
def open_app(d,p,c):
    d.adb('shell','am','start','-W','-n',PKG+'/.MainActivity')
    for _ in range(30):
        try:foreground(d);break
        except ValueError:time.sleep(.1)
    else:raise ValueError('NZ Tides did not acquire native focus')
    return table(wait(d,ready))
def read_tides(d,p,c):
    # Explicit cold-read contract: launch only from the proven Samsung HOME.
    # A foreign app or unknown popup still reaches nodes() and fails closed.
    focus=d.adb('shell','dumpsys window | grep -m1 mCurrentFocus')
    if re.search(r'\scom\.sec\.android\.app\.launcher/[^\s}]+',focus):return open_app(d,p,c)
    return table(nodes(d))
def open_ports(d,p,c):
    ns=nodes(d);table(ns);tap(d,find(ns,desc='More options'));ns=wait(d,lambda ns:find(ns,text='Choose Port') and find(ns,text='About'))
    tap(d,find(ns,text='Choose Port'));return ports(wait(d,lambda ns:find(ns,text='Cancel')))
def scroll_ports(d,p,c):
    direction=p.get('direction')
    if direction not in {'down','up'}:raise ValueError('Use down or up in the open public picker')
    ns=nodes(d);before=ports(ns)['ports'];foreground(d)
    d.swipe(540,1800 if direction=='down' else 700,540,700 if direction=='down' else 1800,350)
    return ports(wait(d,lambda ns:ports(ns)['ports']!=before))
def select_port(d,p,c):
    wanted=p.get('port')
    if wanted not in PORTS:raise ValueError('Exact bundled port name required')
    ns=nodes(d)
    if wanted not in ports(ns)['ports']:raise ValueError('Port must currently be exposed; scroll first')
    tap(d,find(ns,text=wanted));return table(wait(d,lambda ns:ready(ns) and table(ns)['port']==wanted))
def tides_ok(d,c):
    try:return c.result==read_tides(d,{},c)
    except ValueError:return False
def ports_ok(d,c):
    try:return c.result==ports(nodes(d))
    except ValueError:return False
