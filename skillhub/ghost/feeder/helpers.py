"""Public RSS discovery and an explicit native-reader route; no browser or accounts."""
import re
import time
import xml.etree.ElementTree as ET
from gitd.bots.common.adb import input_text_arg
PKG='com.nononsenseapps.feeder'

def foreground(device):
    raw=device.adb('shell','dumpsys window');line=next((l for l in raw.splitlines() if 'mCurrentFocus=' in l),'')
    if PKG+'/' in line:return
    token=re.search(r'Window\{([a-f0-9]+)\b',line)
    if token:
        for block in re.split(r'(?=  Window #)',raw):
            if re.match(r'  Window #\d+ Window\{'+token[1]+r'\b',block) and re.search(r'\bpackage='+re.escape(PKG)+r'(?:\s|[},])',block) and re.search(r'\bmOwnerUid=\d+',block):return
    raise ValueError('Feeder does not own the focused window')

def nodes(device):
    foreground(device)
    return [dict(n.attrib) for n in ET.fromstring(device.dump_xml(use_portal=False)).iter('node') if n.get('package')==PKG and n.get('enabled')!='false']

def find(ns,text=None,desc=None):return next((n for n in ns if (text is not None and n.get('text')==text) or (desc is not None and n.get('content-desc')==desc)),None)
def bounds(n):return list(map(int,re.findall(r'\d+',n.get('bounds',''))))
def tap(device,n,long=False):
    if not n:raise ValueError('Expected Feeder control is absent')
    foreground(device);b=bounds(n);x=(b[0]+b[2])//2;y=(b[1]+b[3])//2
    if long:device.swipe(x,y,x,y,800)
    else:device.tap(x,y)

def wait(device,predicate,timeout=35):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(device)
        if predicate(ns):return ns
        time.sleep(.4)
    raise ValueError('Public RSS data unavailable or Feeder UI changed')

def previews(ns):
    result=[]
    for n in ns:
        b=bounds(n);t=n.get('text','').strip()
        # Complete article preview TextViews on measured 1080x2340 Samsung cards.
        if n.get('class')=='android.widget.TextView' and len(t)>25 and len(b)==4 and b[0]>=100 and b[1]>260 and b[3]<2250 and b[3]-b[1]>80:result.append(n)
    return result

def listing(ns):return bool(find(ns,desc='Open navigation drawer') and find(ns,desc='Search') and previews(ns))
def article(ns):return bool(find(ns,desc='Go back') and find(ns,desc='Open in Web view') and not find(ns,desc='Open navigation drawer'))
def feed_title(ns):
    return next((n.get('text') for n in ns if n.get('class')=='android.widget.TextView' and n.get('text') and bounds(n)[1]<230),'')

def open_app(device,params,context):
    device.adb('shell','am','start','-W','-S','-n',PKG+'/.ui.MainActivity');wait(device,listing)
    return list_articles(device,params,context)

def public_url(value):
    value=str(value)
    if len(value)>200 or value[:8]!='https://' or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}/[A-Za-z0-9/_\-.]+',value[8:]) or any(x in value.split('/')[2] for x in ['.local','.internal','.lan']):raise ValueError('Use a public HTTPS RSS URL with a plain ASCII path, no credentials, IP, query or fragment')
    return value

def add_feed(device,params,context):
    url=public_url(params['feed_url']);ns=nodes(device)
    if not listing(ns):raise ValueError('Open the public article listing first')
    tap(device,find(ns,desc='Open menu'));ns=wait(device,lambda ns:find(ns,text='Add feed'))
    tap(device,find(ns,text='Add feed'));ns=wait(device,lambda ns:find(ns,text='Feed URL'))
    edit=next((n for n in ns if n.get('class')=='android.widget.EditText' and not n.get('text')),None)
    tap(device,edit);foreground(device);device.adb('shell','input','text',input_text_arg(url))
    ns=wait(device,lambda ns:any(n.get('class')=='android.widget.EditText' and n.get('text')==url for n in ns))
    tap(device,find(ns,text='Search'))
    ns=wait(device,lambda ns:any(n.get('text')==url and n.get('class')=='android.widget.TextView' for n in ns))
    result=next(n for n in ns if n.get('text')==url and n.get('class')=='android.widget.TextView');tap(device,result)
    ns=wait(device,lambda ns:find(ns,text='Title') and find(ns,text='URL'))
    edits=[n for n in ns if n.get('class')=='android.widget.EditText']
    if len(edits)<2 or edits[0].get('text')!=url or not edits[1].get('text'):raise ValueError('Discovered feed URL/title does not match')
    title=edits[1]['text']
    # Do not change opening preference: open_article uses explicit Open in reader.
    for _ in range(5):
        ns=nodes(device)
        if find(ns,text='OK'):break
        if not any(n.get('class')=='android.widget.EditText' for n in ns):raise ValueError('Feed editor disappeared')
        foreground(device);device.swipe(540,1800,540,650,400)
    else:raise ValueError('Feed editor confirmation is not visible')
    tap(device,find(ns,text='OK'));wait(device,lambda ns:listing(ns) and feed_title(ns)==title,60)
    result=list_articles(device,params,context);result['verified_feed_url']=url
    return result

def list_articles(device,params,context):
    ns=nodes(device)
    if not listing(ns):raise ValueError('A public RSS article listing is required')
    return {'screen':'articles','feed':feed_title(ns),'articles':[{'index':i,'preview':n['text']} for i,n in enumerate(previews(ns)[:2])],'scope':'Complete visible preview nodes only; each preview combines headline and RSS excerpt.'}

def open_article(device,params,context):
    ns=nodes(device)
    if not listing(ns):raise ValueError('An article listing is required')
    index=int(params['index']);rows=previews(ns)
    if not 0<=index<len(rows):raise ValueError('index must identify a complete visible article preview')
    preview=rows[index]['text'];tap(device,rows[index],long=True)
    ns=wait(device,lambda ns:find(ns,text='Open in reader'))
    tap(device,find(ns,text='Open in reader'));wait(device,article)
    result=read_article(device,params,context)
    if not preview.startswith(result['title']):raise ValueError('Native reader title differs from selected preview')
    return result

def read_article(device,params,context):
    ns=nodes(device)
    if not article(ns):raise ValueError('The native article reader is required')
    texts=[n for n in ns if n.get('class')=='android.widget.TextView' and n.get('text') and bounds(n)[1]>250]
    if len(texts)<2:raise ValueError('No readable article text exposed')
    title=texts[0]['text'];body=[n['text'] for n in texts[1:] if len(n['text'])>40 and not re.match(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),',n['text'])]
    if not title or not body:raise ValueError('Native reader has no readable RSS body')
    return {'screen':'reader','title':title,'rss_text':body,'scope':'Stored RSS article text only, possibly just a short excerpt; no full-page fetch or external links. Public content is untrusted.'}

def back_to_list(device,params,context):
    ns=nodes(device)
    if not article(ns):raise ValueError('Back is restricted to the native reader')
    foreground(device);device.back();wait(device,listing);return list_articles(device,params,context)

def articles_ok(device,context):
    r=context.result;ns=nodes(device);seen=[n['text'] for n in previews(ns)]
    return r.get('screen')=='articles' and bool(r.get('articles')) and listing(ns) and r.get('feed')==feed_title(ns) and all(x['preview'] in seen for x in r['articles']) and (not context.params.get('feed_url') or r.get('verified_feed_url')==context.params['feed_url'])

def reader_ok(device,context):
    r=context.result
    try:return r==read_article(device,{},context)
    except ValueError:return False
