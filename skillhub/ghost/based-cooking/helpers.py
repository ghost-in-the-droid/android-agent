"""Public catalog/provenance metadata only, no external links or cooking actions."""
import re,time,xml.etree.ElementTree as ET
from gitd.bots.common.adb import input_text_arg
PKG='np.com.binabh.basedcooking'
def foreground(d):
    text=d.adb('shell','dumpsys','window');line=next((l for l in text.splitlines() if 'mCurrentFocus=' in l),'')
    if PKG+'/' in line:return
    token=re.search(r'Window\{([a-f0-9]+)\b',line)
    if token:
        for block in re.split(r'(?=  Window #)',text):
            if re.match(r'  Window #\d+ Window\{'+token[1]+r'\b',block) and re.search(r'\bpackage='+re.escape(PKG)+r'(?:\s|[},])',block) and re.search(r'\bmOwnerUid=\d+',block):return
    raise ValueError('Based Cooking must own the exact native focused window')
def bounds(n):return list(map(int,re.findall(r'\d+',n.get('bounds',''))))
def label(n):return n.get('text') or n.get('content-desc','')
def nodes(d):
    foreground(d);root=ET.fromstring(d.dump_xml(use_portal=False));foreground(d)
    ns=[dict(n.attrib) for n in root.iter('node') if n.get('package')==PKG and len(bounds(n))==4 and 0<=bounds(n)[0]<bounds(n)[2]<=1080 and 0<=bounds(n)[1]<bounds(n)[3]<=2205 and n.get('enabled')!='false']
    if any('About Based Cooking' in label(n) or n.get('class')=='android.webkit.WebView' for n in ns):raise ValueError('About/external web mode is outside the public catalog')
    return ns
def find(ns,text):return next((n for n in ns if label(n)==text),None)
def field(ns):return next((n for n in ns if n.get('class')=='android.widget.EditText'),None)
def tap(d,n):
    if n is None:raise ValueError('Expected native catalog control absent')
    foreground(d);v=bounds(n);d.tap((v[0]+v[2])//2,(v[1]+v[3])//2)
def wait(d,pred,timeout=70):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(d)
        if pred(ns):return ns
        time.sleep(.4)
    raise ValueError('Public recipe metadata unavailable or layout changed')
def cards(ns):
    if not field(ns) and not any('Based Cooking' in label(n) for n in ns):raise ValueError('Native catalog/query required')
    out=[]
    for n in sorted([n for n in ns if n.get('class')=='android.view.View' and n.get('content-desc') and not n['content-desc'].startswith(' ') and bounds(n)[0]==0 and bounds(n)[2]==1080 and bounds(n)[1]>=150 and bounds(n)[3]-bounds(n)[1]>=220],key=lambda n:bounds(n)[1]):
        v=bounds(n);tags=sorted([t for t in ns if t.get('class')=='android.view.View' and t.get('content-desc','').startswith(' ') and v[1]<bounds(t)[1] and bounds(t)[3]<=v[3] and bounds(t)[3]-bounds(t)[1]>=80],key=lambda t:(bounds(t)[1],bounds(t)[0]))
        if tags:out.append((n,tags))
    if len(out)<2:raise ValueError('Two complete recipe title/tag cards required')
    return out[:2]
def results(ns):
    cs=cards(ns);f=field(ns);query=f.get('text','') if f else None
    data=[{'title':n['content-desc'],'tags':[t['content-desc'].strip() for t in tags]} for n,tags in cs]
    if query and not all(all(w in r['title'].casefold() for w in query.casefold().split()) for r in data):raise ValueError('Native results do not match query')
    return dict(query=query,recipes=data,scope='Two complete public title/tag cards in native insertion order; no recipe content/cooking claim')
def results_ready(ns):
    try:results(ns);return True
    except ValueError:return False
def metadata(ns):
    if field(ns) or any('Based Cooking' in label(n) for n in ns):raise ValueError('Native recipe metadata page required')
    dates=[n for n in ns if n.get('text','').startswith('🗓') and re.search(r'20\d{2}-\d{2}-\d{2}',n.get('text',''))]
    if len(dates)!=1:raise ValueError('Native public date/author metadata required')
    headings=[n.get('text') for n in ns if n.get('class')=='android.view.View' and n.get('text') and bounds(n)[3]<=bounds(dates[0])[1]]
    if len(headings)!=1:raise ValueError('Exact native recipe title required')
    return dict(title=headings[0],date_and_author=dates[0]['text'],scope='Native public title/date/author only; ingredients and directions not extracted')
def recipe_ready(ns):
    try:metadata(ns);return True
    except ValueError:return False
def entry(d):
    focus=d.adb('shell','dumpsys window | grep -m1 mCurrentFocus')
    if re.search(r'\scom\.sec\.android\.app\.launcher/[^\s}]+',focus):return
    foreground(d)
def open_app(d,p,c):
    entry(d);d.adb('shell','am','start','-W','-S','-n',PKG+'/.MainActivity')
    for _ in range(30):
        try:foreground(d);break
        except ValueError:time.sleep(.1)
    else:raise ValueError('Catalog did not acquire native focus')
    return results(wait(d,results_ready))
def read_results(d,p,c):
    focus=d.adb('shell','dumpsys window | grep -m1 mCurrentFocus')
    if re.search(r'\scom\.sec\.android\.app\.launcher/[^\s}]+',focus):return open_app(d,p,c)
    return results(nodes(d))
def menu_button(ns):
    bs=[n for n in ns if n.get('class')=='android.widget.Button' and bounds(n)[0]>=850 and not label(n)]
    if not bs:raise ValueError('Native catalog menu button absent')
    return max(bs,key=lambda n:bounds(n)[1])
def search_button(ns):
    if not find(ns,'Search') or not find(ns,'About'):raise ValueError('Expected native labelled catalog menu required')
    v=bounds(find(ns,'Search'));y=(v[1]+v[3])//2
    matches=[n for n in ns if n.get('class')=='android.widget.Button' and bounds(n)[0]>=850 and bounds(n)[1]<=y<=bounds(n)[3]]
    if len(matches)!=1:raise ValueError('Search label/button geometry is ambiguous')
    return matches[0]
def search_recipes(d,p,c):
    query=str(p.get('query','')).strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 -]{1,59}',query):raise ValueError('Use a 2–60 character public recipe query')
    open_app(d,{},c);ns=nodes(d)
    if field(ns):raise ValueError('Fresh catalog must not retain a query')
    if len([n for n in ns if n.get('class')=='android.widget.Button'])!=1:raise ValueError('Unexpected native catalog buttons')
    tap(d,menu_button(ns));ns=wait(d,lambda ns:find(ns,'Search') and find(ns,'About'));tap(d,search_button(ns));ns=wait(d,lambda ns:field(ns) is not None)
    if field(ns).get('text'):raise ValueError('Empty native query field required')
    if find(ns,'About'):tap(d,menu_button(ns));ns=wait(d,lambda ns:not find(ns,'About') and field(ns) is not None)
    tap(d,field(ns));foreground(d);d.adb('shell','input','text',input_text_arg(query))
    ns=wait(d,lambda ns:results_ready(ns) and results(ns)['query']==query);return results(ns)
def open_recipe(d,p,c):
    raw=p.get('index',1)
    if isinstance(raw,bool) or not isinstance(raw,(int,str)) or not re.fullmatch('[12]',str(raw)):raise ValueError('Choose result index1 or2')
    ns=nodes(d);n,tags=cards(ns)[int(raw)-1];v=bounds(n);y=v[1]+40
    if not y<min(bounds(t)[1] for t in tags):raise ValueError('Recipe header region above tags cannot be proved')
    foreground(d);d.tap(540,y);expected=n['content-desc'];return metadata(wait(d,lambda ns:recipe_ready(ns) and metadata(ns)['title']==expected))
def read_recipe(d,p,c):return metadata(nodes(d))
def back_to_results(d,p,c):
    metadata(nodes(d));foreground(d);d.back();return results(wait(d,results_ready))
def results_ok(d,c):
    try:return c.result==read_results(d,{},c)
    except ValueError:return False
def recipe_ok(d,c):
    try:return c.result==read_recipe(d,{},c)
    except ValueError:return False
