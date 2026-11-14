"""Public program metadata only; reminders are never touched."""
import re,time,xml.etree.ElementTree as ET
PKG='net.gaast.giggity'
def foreground(d):
    text=d.adb('shell','dumpsys','window');line=next((l for l in text.splitlines() if 'mCurrentFocus=' in l),'')
    if PKG+'/' in line:return
    token=re.search(r'Window\{([a-f0-9]+)\b',line)
    if token:
        for block in re.split(r'(?=  Window #)',text):
            if re.match(r'  Window #\d+ Window\{'+token[1]+r'\b',block) and re.search(r'\bpackage='+re.escape(PKG)+r'(?:\s|[},])',block) and re.search(r'\bmOwnerUid=\d+',block):return
    raise ValueError('Giggity must own the exact native focused window')
def bounds(n):return list(map(int,re.findall(r'\d+',n.get('bounds',''))))
def nodes(d):
    foreground(d);root=ET.fromstring(d.dump_xml(use_portal=False));foreground(d)
    return [dict(n.attrib) for n in root.iter('node') if n.get('package')==PKG and len(bounds(n))==4 and 0<=bounds(n)[0]<bounds(n)[2]<=1080 and 0<=bounds(n)[1]<bounds(n)[3]<=2205 and n.get('enabled')!='false']
def find(ns,text=None,desc=None,rid=None):return next((n for n in ns if (text is None or n.get('text')==text) and (desc is None or n.get('content-desc')==desc) and (rid is None or n.get('resource-id')==PKG+':id/'+rid)),None)
def tap(d,n):
    if n is None or n.get('class')=='android.widget.CheckBox':raise ValueError('Missing native control or forbidden reminder input')
    foreground(d);v=bounds(n);d.tap((v[0]+v[2])//2,(v[1]+v[3])//2)
def wait(d,pred,timeout=55):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(d)
        if pred(ns):return ns
        time.sleep(.3)
    raise ValueError('Public catalog/program unavailable or changed')
def catalog_rows(ns):
    if not find(ns,text='Giggity') or not find(ns,desc='Settings') or not find(ns,desc='Add...'):raise ValueError('Preconfigured catalog required')
    titles=sorted([n for n in ns if n.get('resource-id')==PKG+':id/title'],key=lambda n:bounds(n)[1]);out=[]
    for n in titles:
        ds=[d for d in ns if d.get('resource-id')==PKG+':id/subtitle' and bounds(d)[1]==bounds(n)[3] and re.search(r'20\d{2}',d.get('text',''))]
        if len(ds)==1 and n.get('text'):out.append((n,ds[0]))
    if len(out)<3:raise ValueError('Three complete native conference/date rows required')
    return out
def catalog(ns):return dict(conferences=[{'name':n['text'],'date_range':d['text']} for n,d in catalog_rows(ns)[:3]],scope='Current native public preconfigured catalog/date text; no personal calendar or freshness guarantee')
def catalog_ready(ns):
    try:catalog(ns);return True
    except ValueError:return False
def program_nodes(ns):
    if not find(ns,desc='Show drawer') or not find(ns,desc='Search') or find(ns,text='Remind me'):raise ValueError('Public program view required')
    headers=[n['text'] for n in ns if n.get('class')=='android.widget.TextView' and re.match(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{1,2} [A-Za-z]+, ',n.get('text','')) and bounds(n)[1]<230]
    sessions=sorted([n for n in ns if n.get('class')=='android.widget.TextView' and n.get('text') and bounds(n)[0]>=180 and bounds(n)[1]>=286 and bounds(n)[3]-bounds(n)[1]>=60 and bounds(n)[2]-bounds(n)[0]>=100],key=lambda n:(bounds(n)[1],bounds(n)[0]))
    if len(headers)!=1 or not sessions:raise ValueError('Native program header and session labels required')
    return headers[0],sessions[:12]
def program(ns):
    header,sessions=program_nodes(ns);return dict(displayed_header=header,exposed_session_titles=[n['text'] for n in sessions],scope='Exposed native labels only; no grid-duration/room inference or time-zone conversion')
def program_ready(ns):
    try:program(ns);return True
    except ValueError:return False
def details(ns):
    check=find(ns,text='Remind me')
    title=find(ns,rid='title');room=find(ns,rid='room');clock=find(ns,rid='time');body=find(ns,rid='description')
    if check is None or check.get('class')!='android.widget.CheckBox' or check.get('checked')!='false' or not all([title,room,clock,body]) or not all(n.get('text') for n in [title,room,clock]):raise ValueError('Read-only session detail with reminder explicitly off required')
    text=body.get('text','');return dict(title=title['text'],room=room['text'],displayed_time=clock['text'],description_preview=text[:400],description_truncated=len(text)>400,reminder_enabled=False,scope='Public native detail; displayed time copied without zone/end-date inference, links never followed')
def detail_ready(ns):
    try:details(ns);return True
    except ValueError:return False
def open_app(d,p,c):
    focus=d.adb('shell','dumpsys window | grep -m1 mCurrentFocus')
    if not re.search(r'\scom\.sec\.android\.app\.launcher/[^\s}]+',focus):foreground(d)
    d.adb('shell','pm','revoke',PKG,'android.permission.POST_NOTIFICATIONS');d.adb('shell','pm','set-permission-flags',PKG,'android.permission.POST_NOTIFICATIONS','user-set','user-fixed')
    d.adb('shell','am','start','-W','-S','-n',PKG+'/.ChooserActivity')
    for _ in range(30):
        try:foreground(d);break
        except ValueError:time.sleep(.1)
    else:raise ValueError('Giggity did not acquire native focus')
    return catalog(wait(d,lambda ns:catalog_ready(ns) and find(ns,text='Later') is not None))
def read_catalog(d,p,c):
    focus=d.adb('shell','dumpsys window | grep -m1 mCurrentFocus')
    if re.search(r'\scom\.sec\.android\.app\.launcher/[^\s}]+',focus):return open_app(d,p,c)
    return catalog(nodes(d))
def open_conference(d,p,c):
    wanted=p.get('name');ns=nodes(d);rows=catalog_rows(ns);matches=[n for n,_ in rows if n.get('text')==wanted]
    if len(matches)!=1:raise ValueError('Exact unique exposed preconfigured conference required')
    tap(d,matches[0]);return program(wait(d,lambda ns:program_ready(ns) and wanted in program(ns)['displayed_header']))
def read_program(d,p,c):return program(nodes(d))
def open_session(d,p,c):
    wanted=p.get('title');ns=nodes(d);_,sessions=program_nodes(ns);matches=[n for n in sessions if n.get('text')==wanted]
    if len(matches)!=1:raise ValueError('Exact unique exposed session title required')
    chosen=matches[0];v=bounds(chosen);x=v[0]+20;y=v[1]+20
    if any(n is not chosen and (b:=bounds(n))[0]<=x<=b[2] and b[1]<=y<=b[3] for n in sessions):raise ValueError('Overlapping native session tap is ambiguous')
    foreground(d);d.tap(x,y);return details(wait(d,lambda ns:detail_ready(ns) and details(ns)['title']==wanted))
def read_session(d,p,c):return details(nodes(d))
def close_session(d,p,c):
    details(nodes(d));foreground(d);d.back();return program(wait(d,program_ready))
def catalog_ok(d,c):
    try:return c.result==read_catalog(d,{},c)
    except ValueError:return False
def program_ok(d,c):
    try:return c.result==read_program(d,{},c)
    except ValueError:return False
def session_ok(d,c):
    try:return c.result==read_session(d,{},c)
    except ValueError:return False
