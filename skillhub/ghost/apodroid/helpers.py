"""NASA caption only. Wallpaper writes/background execution denied before launch."""
import re,time,datetime,xml.etree.ElementTree as ET
PKG='io.github.buerlino.apodroid'
OPS=('WRITE_WALLPAPER','RUN_ANY_IN_BACKGROUND')
def protected(d):
    for op in OPS:
        if not re.search(r'\bignore\b',d.adb('shell','appops','get',PKG,op)):raise ValueError('APOD wallpaper/background app-op guard is required')
def foreground(d):
    if PKG+'/' not in d.adb('shell','dumpsys window | grep -m1 mCurrentFocus'):raise ValueError('APODroid must own native focus')
def bounds(n):return list(map(int,re.findall(r'\d+',n.get('bounds',''))))
def nodes(d):
    protected(d);foreground(d);root=ET.fromstring(d.dump_xml(use_portal=False));foreground(d)
    ns=[dict(n.attrib) for n in root.iter('node') if n.get('package')==PKG and len(bounds(n))==4 and 0<=bounds(n)[0]<bounds(n)[2]<=1080 and 0<=bounds(n)[1]<bounds(n)[3]<=2205 and n.get('enabled')!='false']
    if any(n.get('class') in {'android.view.SurfaceView','android.view.TextureView','android.widget.VideoView'} or n.get('content-desc') in {'Saved','Set as wallpaper','Pause','Play'} for n in ns):raise ValueError('Saved/crop/player mode is outside the caption reader')
    return ns
def find(ns,desc):return next((n for n in ns if n.get('content-desc')==desc),None)
def picture(ns):
    images=[n for n in ns if n.get('class')=='android.widget.ImageView' and n.get('content-desc')]
    dates=[n for n in ns if n.get('class')=='android.widget.TextView' and re.fullmatch(r'\d{1,2} [A-Za-z]+ \d{4}(?: · Video)?',n.get('text',''))]
    if len(images)!=1 or len(dates)!=1 or not any(n.get('text')==images[0]['content-desc'] for n in ns) or not (find(ns,'Show explanation') or find(ns,'Hide explanation')):raise ValueError('Native picture/title/date/explanation controls required')
    date=dates[0]['text'];iso=datetime.datetime.strptime(date.split(' · ')[0],'%d %B %Y').date().isoformat()
    return {'title':images[0]['content-desc'],'displayed_date':date,'date':iso,'media_type':'static_video_day_frame' if ' · Video' in date else 'image','explanation_expanded':find(ns,'Hide explanation') is not None,'scope':'Public NASA title/date only; no wallpaper, save, browser or media playback. Displayed date is not a freshness guarantee.'}
def explanation(ns):
    r=picture(ns)
    if not r['explanation_expanded']:raise ValueError('Explanation is not expanded')
    date=next(n for n in ns if n.get('text')==r['displayed_date'])
    bodies=sorted([n for n in ns if n.get('class')=='android.widget.TextView' and n.get('clickable')=='true' and len(n.get('text',''))>=80 and bounds(n)[1]>=bounds(date)[3]],key=lambda n:bounds(n)[1])
    if not bodies:raise ValueError('Native explanation text is absent')
    return {**r,'explanation':bodies[0]['text'],'scope':'Native exposed astronomer explanation; may extend beyond viewport. Public untrusted data, no links followed.'}
def wait(d,predicate,timeout=40):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(d)
        if predicate(ns):return ns
        time.sleep(.5)
    raise ValueError('NASA picture/explanation unavailable or expected UI changed')
def ready(ns):
    try:return bool(picture(ns))
    except ValueError:return False
def tap_control(d,ns,desc):
    if desc not in {'Show explanation','Hide explanation'}:raise ValueError('Only explanation toggles are permitted')
    picture(ns);n=find(ns,desc)
    if n is None:raise ValueError('Expected explanation toggle absent')
    protected(d);foreground(d);v=bounds(n);d.tap((v[0]+v[2])//2,(v[1]+v[3])//2)
def open_app(d,p,c):
    for op in OPS:d.adb('shell','appops','set',PKG,op,'ignore')
    protected(d);d.adb('shell','am','start','-W','-S','-n',PKG+'/.MainActivity')
    for _ in range(30):
        try:foreground(d);break
        except ValueError:time.sleep(.1)
    else:raise ValueError('APODroid did not acquire native focus')
    return picture(wait(d,ready))
def read_picture(d,p,c):return picture(nodes(d))
def read_explanation(d,p,c):
    ns=nodes(d);r=picture(ns)
    if not r['explanation_expanded']:tap_control(d,ns,'Show explanation');ns=wait(d,lambda ns:find(ns,'Hide explanation') is not None)
    return explanation(ns)
def hide_explanation(d,p,c):
    ns=nodes(d);explanation(ns);tap_control(d,ns,'Hide explanation');return picture(wait(d,lambda ns:find(ns,'Show explanation') is not None))
def picture_ok(d,c):
    try:return c.result==read_picture(d,{},c)
    except ValueError:return False
def explanation_ok(d,c):
    try:return c.result==explanation(nodes(d))
    except ValueError:return False
