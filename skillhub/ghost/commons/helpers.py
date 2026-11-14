"""Anonymous Featured captions only; image details hit low-memory termination."""
import re
import time
import xml.etree.ElementTree as ET
PKG='fr.free.nrw.commons'
def foreground(device):
    if PKG+'/' not in device.adb('shell','dumpsys window | grep -m1 mCurrentFocus'):raise ValueError('Commons must own native focus')
def bounds(n):return list(map(int,re.findall(r'\d+',n.get('bounds',''))))
def nodes(device):
    foreground(device);root=ET.fromstring(device.dump_xml(use_portal=False));foreground(device)
    return [dict(n.attrib) for n in root.iter('node') if n.get('package')==PKG and len(bounds(n))==4 and 0<=bounds(n)[0]<bounds(n)[2]<=1080 and 0<=bounds(n)[1]<bounds(n)[3]<=2205 and n.get('enabled')!='false']
def find(ns,text=None,id=None,desc=None):return next((n for n in ns if (text is None or n.get('text')==text) and (id is None or n.get('resource-id')==PKG+':id/'+id) and (desc is None or n.get('content-desc')==desc)),None)
def tap(device,n):
    if n is None:raise ValueError('Expected anonymous Commons control absent')
    foreground(device);v=bounds(n);device.tap((v[0]+v[2])//2,(v[1]+v[3])//2)
def wait(device,predicate,timeout=35):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(device)
        if predicate(ns):return ns
        time.sleep(.5)
    raise ValueError('Featured feed unavailable or expected anonymous screen changed')
def selected(ns,desc):return any(n.get('content-desc')==desc and n.get('selected')=='true' for n in ns)
def featured(ns):return selected(ns,'Explore') and selected(ns,'FEATURED') and find(ns,id='action_search') is not None and find(ns,id='mediaDetailTitle') is None

def entries(ns):
    if not featured(ns):raise ValueError('Selected Explore/Featured list required; no image details, map or bookmarks')
    titles=sorted([n for n in ns if n.get('resource-id')==PKG+':id/categoryImageTitle' and n.get('text') and 293<=bounds(n)[1]<bounds(n)[3]<=2047],key=lambda n:bounds(n)[1]);result=[]
    for title in titles:
        credits=[n for n in ns if n.get('resource-id')==PKG+':id/categoryImageAuthor' and n.get('text') and bounds(title)[1]<bounds(n)[1] and abs(bounds(n)[1]-bounds(title)[3])<=90 and bounds(n)[3]<=2047]
        if len(credits)==1:result.append({'caption':title['text'],'credit':credits[0]['text']})
    if len(result)<2:raise ValueError('Two exposed caption/credit pairs required')
    return {'screen':'Featured','images':result[:2],'scope':'Exposed public caption/credit pairs only; no image detail, file, license assessment or phone-account data.'}
def ready(ns):
    try:return bool(entries(ns))
    except ValueError:return False

def open_app(device,params,context):
    device.adb('shell','am','start','-W','-S','-n',PKG+'/fr.free.nrw.commons.auth.LoginActivity')
    for _ in range(30):
        try:foreground(device);break
        except ValueError:time.sleep(.1)
    else:raise ValueError('Commons did not acquire native focus')
    ns=nodes(device)
    if find(ns,id='skip_login') and find(ns,id='login_username'):
        tap(device,find(ns,id='skip_login'));ns=wait(device,lambda ns:find(ns,text='Do you really want to skip log-in?') is not None)
        if not find(ns,text='You will have to log in to upload pictures in the future.'):raise ValueError('Unexpected skip-login confirmation')
        tap(device,find(ns,text='YES'))
    return entries(wait(device,ready))
def read_featured(device,params,context):return entries(nodes(device))
def scroll_featured(device,params,context):
    direction=params['direction']
    if direction not in {'down','up'}:raise ValueError('direction must be down or up')
    ns=nodes(device);entries(ns);foreground(device)
    device.swipe(540,1800,540,700,350) if direction=='down' else device.swipe(540,700,540,1800,350)
    return entries(wait(device,ready))
def featured_ok(device,context):
    try:return context.result==read_featured(device,{},context)
    except ValueError:return False
