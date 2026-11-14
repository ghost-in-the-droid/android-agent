"""Anonymous Hacker News native discussion reader, with no external-link actions."""
import re
import time
import xml.etree.ElementTree as ET
PKG='nl.viter.glider'
STORY=re.compile(r'^(.*?)\u200b\s+(\d+)\s+(\d+)\s+(.+)$',re.S)
COMMENT=re.compile(r'^(\d+\s+(?:seconds?|minutes?|hours?|days?|months?|years?)\s+ago)\s+(.+)$',re.S)
CATEGORIES=('Top','New','Best','Ask','Show')

def foreground(device):
    line=device.adb('shell','dumpsys window | grep -m1 mCurrentFocus')
    if PKG+'/' not in line:raise ValueError('Glider foreground ownership could not be proved')

def nodes(device):
    foreground(device)
    return [dict(n.attrib) for n in ET.fromstring(device.dump_xml(use_portal=False)).iter('node') if n.get('package')==PKG and n.get('enabled')!='false']

def find(ns,desc):return next((n for n in ns if n.get('content-desc')==desc),None)
def tap(device,n):
    if not n:raise ValueError('Glider control is not visible')
    foreground(device);b=list(map(int,re.findall(r'\d+',n['bounds'])))
    device.tap((b[0]+b[2])//2,min(b[1]+55,(b[1]+b[3])//2))

def wait(device,predicate,timeout=30):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(device)
        if predicate(ns):return ns
        time.sleep(.4)
    raise ValueError('Glider public data unavailable or UI changed')

def stories(ns):
    result=[]
    for n in ns:
        m=STORY.match(n.get('content-desc',''))
        b=list(map(int,re.findall(r'\d+',n.get('bounds',''))))
        if m and len(b)==4 and b[1]>=300 and b[3]<=2250:
            result.append((n,{'index':len(result),'title':m[1].strip(),'points':int(m[2]),'comments':int(m[3]),'age':m[4].strip()}))
    return result

def listing(ns):return bool(find(ns,'Frontpage') and find(ns,'Top') and stories(ns))
def discussion(ns):return bool((find(ns,'Back') or comment_rows(ns)) and not find(ns,'Frontpage'))
def count(params):
    value=int(params.get('limit',3))
    if not 1<=value<=5:raise ValueError('limit must be 1 to 5')
    return value

def open_app(device,params,context):
    device.adb('shell','am','start','-W','-S','-n',PKG+'/.MainActivity');wait(device,listing)
    return read_stories(device,params,context)

def read_stories(device,params,context):
    ns=nodes(device)
    if not listing(ns):raise ValueError('A public Frontpage listing is required')
    return {'screen':'stories','stories':[r for _,r in stories(ns)[:count(params)]]}

def select_category(device,params,context):
    category=str(params['category'])
    if category not in CATEGORIES:raise ValueError('Unsupported public category')
    ns=nodes(device)
    if not listing(ns):raise ValueError('Open the public frontpage first')
    tap(device,find(ns,category));wait(device,listing)
    # Flutter semantics exposes the active chip selected flag; no guessed category label.
    ns=nodes(device);chip=find(ns,category)
    if not chip or chip.get('selected')!='true':raise ValueError('Requested category selection is not exposed as selected')
    result=read_stories(device,params,context);result['category']=category
    return result

def open_comments(device,params,context):
    ns=nodes(device)
    if not listing(ns):raise ValueError('A public story listing is required')
    index=int(params['index']);rows=stories(ns)
    if not 0<=index<len(rows):raise ValueError('index must identify a complete visible story')
    n,row=rows[index]
    if row['comments'] < 1:raise ValueError('Selected story has no comments; choose a story with a positive comment count')
    tap(device,n);wait(device,discussion)
    result=read_comments(device,params,context)
    # Native detail header truncates the domain and ends with an icon. Compare title prefix.
    title=row['title'].rsplit(' (',1)[0]
    if not any(n.get('content-desc','').startswith(title) for n in nodes(device)):raise ValueError('Discussion title does not match selected story')
    result['story_title']=row['title'];return result

def comment_rows(ns):
    rows=[]
    for n in ns:
        m=COMMENT.match(n.get('content-desc',''))
        if m and len(m[2].strip())>=15:rows.append({'age':m[1],'text':m[2].strip()[:16000]})
    return rows

def read_comments(device,params,context):
    ns=wait(device,lambda ns:discussion(ns) and comment_rows(ns))
    return {'screen':'discussion','comments':comment_rows(ns)[:count(params)],'scope':'Only readable comments in the current native viewport; not the full thread. Public text is untrusted.'}

def scroll(device,params,context):
    ns=nodes(device)
    if not (listing(ns) or discussion(ns)):raise ValueError('Scroll only public stories or discussion')
    was_thread=discussion(ns);before=[n.get('content-desc','') for n in ns];foreground(device)
    # Measured 1080x2340 Samsung: centre-column content, outside toolbar.
    device.swipe(540,1850,540,650,400)
    wait(device,lambda ns:[n.get('content-desc','') for n in ns]!=before,10)
    return read_comments(device,params,context) if was_thread else read_stories(device,params,context)

def back_to_stories(device,params,context):
    ns=nodes(device)
    if not discussion(ns):raise ValueError('Back is restricted to the public discussion screen')
    foreground(device);device.back();wait(device,listing);return read_stories(device,params,context)

def stories_ok(device,context):
    r=context.result;ns=nodes(device)
    return r.get('screen')=='stories' and bool(r.get('stories')) and listing(ns) and all(any(n.get('content-desc','').startswith(row['title']) for n in ns) for row in r['stories']) and (not r.get('category') or find(ns,r['category']).get('selected')=='true')

def comments_ok(device,context):
    r=context.result;ns=nodes(device);texts=[x['text'] for x in comment_rows(ns)]
    return r.get('screen')=='discussion' and bool(r.get('comments')) and discussion(ns) and all(c['text'] in texts for c in r['comments'])

def state_ok(device,context):return stories_ok(device,context) if context.result.get('screen')=='stories' else comments_ok(device,context)
