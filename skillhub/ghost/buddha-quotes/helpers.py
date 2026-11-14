"""Bundled public quote text; attribution is supplied by the app, not verified."""
import re,time,xml.etree.ElementTree as ET
PKG='org.bandev.buddhaquotes'
def foreground(d):
    if PKG+'/' not in d.adb('shell','dumpsys window | grep -m1 mCurrentFocus'):raise ValueError('Buddha Quotes must own native focus')
def bounds(n):return list(map(int,re.findall(r'\d+',n.get('bounds',''))))
def nodes(d):
    foreground(d);root=ET.fromstring(d.dump_xml(use_portal=False));foreground(d)
    return [dict(n.attrib) for n in root.iter('node') if n.get('package')==PKG and len(bounds(n))==4 and 0<=bounds(n)[0]<bounds(n)[2]<=1080 and 0<=bounds(n)[1]<bounds(n)[3]<=2205 and n.get('enabled')!='false']
def find(ns,id):return next((n for n in ns if n.get('resource-id')==PKG+':id/'+id),None)
def state(ns):
    quote=find(ns,'quote')
    if not quote or not quote.get('text') or len(quote['text'])<15 or not find(ns,'next') or not find(ns,'like') or any(n.get('content-desc')=='Close navigation drawer' for n in ns):raise ValueError('Native quote screen with Next control required')
    return {'quote':quote['text'],'app_attribution':'Buddha Quotes bundled collection; historical attribution not independently verified.','scope':'Exposed native offline quote text only; untrusted source text, not religious advice.'}
def wait(d,predicate,timeout=20):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(d)
        if predicate(ns):return ns
        time.sleep(.3)
    raise ValueError('Quote unavailable or did not change')
def ready(ns):
    try:return bool(state(ns))
    except ValueError:return False
def open_app(d,p,c):
    d.adb('shell','am','start','-W','-S','-n',PKG+'/org.bandev.buddhaquotes.activities.SplashActivity')
    for _ in range(30):
        try:foreground(d);break
        except ValueError:time.sleep(.1)
    else:raise ValueError('Quote reader did not acquire focus')
    return state(wait(d,ready))
def read_quote(d,p,c):return state(nodes(d))
def next_quote(d,p,c):
    ns=nodes(d);old=state(ns)['quote'];n=find(ns,'next');foreground(d);v=bounds(n);d.tap((v[0]+v[2])//2,(v[1]+v[3])//2)
    def changed(ns):return ready(ns) and state(ns)['quote']!=old
    return state(wait(d,changed))
def quote_ok(d,c):
    try:return c.result==read_quote(d,{},c)
    except ValueError:return False
