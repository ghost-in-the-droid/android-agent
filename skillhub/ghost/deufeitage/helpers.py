"""Offline public dates; prove native checked year, never personal calendars."""
import re,time,datetime,xml.etree.ElementTree as ET
PKG='de.micmun.android.deufeitage'
REGIONS={'All holidays','Common holidays','Berlin','Hamburg','Bavaria'}
def foreground(d):
    text=d.adb('shell','dumpsys','window');line=next((l for l in text.splitlines() if 'mCurrentFocus=' in l),'')
    if PKG+'/' in line:return
    token=re.search(r'Window\{([a-f0-9]+)\b',line)
    if token:
        for block in re.split(r'(?=  Window #)',text):
            if re.match(r'  Window #\d+ Window\{'+token[1]+r'\b',block) and re.search(r'\bpackage='+re.escape(PKG)+r'(?:\s|[},])',block) and re.search(r'\bmOwnerUid=\d+',block):return
    raise ValueError('DeuFeiTage must own the exact native focused window')
def bounds(n):return list(map(int,re.findall(r'\d+',n.get('bounds',''))))
def nodes(d):
    foreground(d);root=ET.fromstring(d.dump_xml(use_portal=False));foreground(d);ns=[]
    for n in root.iter('node'):
        if n.get('package')!=PKG or len(bounds(n))!=4 or not (0<=bounds(n)[0]<bounds(n)[2]<=1080 and 0<=bounds(n)[1]<bounds(n)[3]<=2205) or n.get('enabled')=='false':continue
        a=dict(n.attrib)
        if n.get('checkable')=='true' and n.get('checked')=='true':
            years=[c.get('text') for c in n.iter('node') if c.get('package')==PKG and re.fullmatch(r'20\d{2}',c.get('text',''))]
            if len(years)==1:a['checked_year']=years[0]
        ns.append(a)
    return ns
def find(ns,text):return next((n for n in ns if n.get('text')==text),None)
def tap(d,n):
    if n is None:raise ValueError('Expected public holiday control missing')
    foreground(d);v=bounds(n);d.tap((v[0]+v[2])//2,(v[1]+v[3])//2)
def wait(d,pred,timeout=25):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(d)
        if pred(ns):return ns
        time.sleep(.2)
    raise ValueError('Expected native public holiday state absent')
def row_nodes(ns):
    years=[int(n['checked_year']) for n in ns if n.get('checked_year')]
    edits=[n for n in ns if n.get('class')=='android.widget.EditText']
    if len(years)!=1 or len(edits)!=1 or edits[0].get('text') not in REGIONS or not all(find(ns,k) for k in ['Date','Holiday','Difference']):raise ValueError('Native checked year, supported region and table headers required')
    year=years[0];out=[]
    for date in sorted([n for n in ns if re.fullmatch(r'[A-Za-z]{3} \d{2}/\d{2}',n.get('text','')) and bounds(n)[0]<250 and bounds(n)[1]>700],key=lambda n:bounds(n)[1]):
        y=bounds(date)[1];names=[n for n in ns if n.get('class')=='android.widget.TextView' and 250<=bounds(n)[0]<850 and bounds(n)[1]==y and n.get('text')];diff=[n for n in ns if bounds(n)[0]>=850 and bounds(n)[1]==y and re.fullmatch(r'-?\d+ days?',n.get('text',''))]
        if len(names)!=1 or len(diff)!=1:continue
        stamp=datetime.datetime.strptime(str(year)+' '+date['text'],'%Y %a %m/%d').date()
        if stamp.strftime('%a')!=date['text'][:3]:raise ValueError('Displayed date weekday does not match checked year')
        out.append((dict(name=names[0]['text'],date=stamp.isoformat(),weekday=date['text'][:3],displayed_date=date['text'],difference=diff[0]['text']),names[0],date))
    if len(out)<3:raise ValueError('Three complete holiday rows required')
    return edits[0]['text'],year,out[:3]
def state(ns):
    region,year,rows=row_nodes(ns);return dict(region=region,year=year,holidays=[r[0] for r in rows],scope='Public app-calculated dates, not independent official verification; no personal calendar access')
def ready(ns):
    try:state(ns);return True
    except ValueError:return False
def index(p):
    value=p.get('index',1)
    if isinstance(value,bool) or not isinstance(value,(int,str)) or not re.fullmatch(r'[123]',str(value)):raise ValueError('Use holiday index1–3')
    return int(value)
def description(ns,ix):
    region,year,rows=row_nodes(ns);row,title,date=rows[ix-1];y=bounds(title)[3];following=[bounds(n)[1] for n in ns if re.fullmatch(r'[A-Za-z]{3} \d{2}/\d{2}',n.get('text','')) and bounds(n)[1]>y];end=min(following) if following else 2205
    bodies=[n.get('text','') for n in ns if n.get('class')=='android.widget.TextView' and len(n.get('text',''))>=60 and bounds(n)[0]<100 and y<bounds(n)[1] and bounds(n)[3]<=end]
    if len(bodies)!=1:raise ValueError('Expected inline description is not expanded')
    return dict(region=region,year=year,index=ix,holiday=row,description=bodies[0],scope='Native public inline description; no external links followed')
def open_app(d,p,c):
    d.adb('shell','am','start','-W','-n',PKG+'/.MainActivity')
    for _ in range(30):
        try:foreground(d);break
        except ValueError:time.sleep(.1)
    else:raise ValueError('Holiday app did not acquire focus')
    return state(wait(d,ready))
def read_state(d,p,c):
    focus=d.adb('shell','dumpsys window | grep -m1 mCurrentFocus')
    if re.search(r'\scom\.sec\.android\.app\.launcher/[^\s}]+',focus):return open_app(d,p,c)
    return state(nodes(d))
def select_region(d,p,c):
    wanted=p.get('region')
    if wanted not in REGIONS:raise ValueError('Use one of the five documented public filters')
    ns=nodes(d);before=state(ns)
    if before['region']==wanted:return before
    tap(d,next(n for n in ns if n.get('class')=='android.widget.EditText'))
    ns=wait(d,lambda ns:find(ns,'All holidays') and find(ns,'Common holidays') and find(ns,wanted));tap(d,find(ns,wanted))
    return state(wait(d,lambda ns:ready(ns) and state(ns)['region']==wanted))
def select_year(d,p,c):
    raw=p.get('year')
    if isinstance(raw,bool) or not isinstance(raw,(int,str)) or not re.fullmatch(r'20\d{2}',str(raw)):raise ValueError('Use an exposed four-digit year')
    year=int(raw)
    ns=nodes(d);before=state(ns);label=next((n for n in ns if n.get('text')==str(year) and 450<=bounds(n)[1]<610),None)
    if label is None:raise ValueError('Year must currently be exposed in the native strip')
    tap(d,label);return state(wait(d,lambda ns:ready(ns) and state(ns)['year']==year and state(ns)['region']==before['region']))
def expand_holiday(d,p,c):
    ix=index(p);ns=nodes(d)
    try:return description(ns,ix)
    except ValueError:pass
    row,title,date=row_nodes(ns)[2][ix-1];tap(d,title)
    def expanded(ns):
        try:description(ns,ix);return True
        except ValueError:return False
    return description(wait(d,expanded),ix)
def collapse_holiday(d,p,c):
    ix=index(p);ns=nodes(d);description(ns,ix);tap(d,row_nodes(ns)[2][ix-1][1])
    def collapsed(ns):
        if not ready(ns):return False
        try:description(ns,ix);return False
        except ValueError:return True
    return state(wait(d,collapsed))
def state_ok(d,c):
    try:return c.result==read_state(d,{},c)
    except ValueError:return False
def details_ok(d,c):
    try:return c.result==description(nodes(d),c.result['index'])
    except (ValueError,KeyError):return False
