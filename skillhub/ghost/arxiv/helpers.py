"""Native public arXiv abstracts only; never download PDFs or follow links."""
import re
import time
import xml.etree.ElementTree as ET
from gitd.bots.common.adb import input_text_arg
PKG='com.gbeatty.arxiv'
ACT=PKG+'/com.gbeatty.arxivexplorer.main.MainActivity'
def foreground(device):
    if PKG+'/' not in device.adb('shell','dumpsys window | grep -m1 mCurrentFocus'):raise ValueError('arXiv must own native focus')
def bounds(n):return list(map(int,re.findall(r'\d+',n.get('bounds',''))))
def nodes(device):
    foreground(device);root=ET.fromstring(device.dump_xml(use_portal=False));foreground(device)
    return [dict(n.attrib) for n in root.iter('node') if n.get('package')==PKG and len(bounds(n))==4 and 0<=bounds(n)[0]<bounds(n)[2]<=1080 and 0<=bounds(n)[1]<bounds(n)[3]<=2205 and n.get('enabled')!='false']
def find(ns,text=None,id=None):return next((n for n in ns if (text is None or n.get('text')==text) and (id is None or n.get('resource-id')==PKG+':id/'+id)),None)
def tap(device,n):
    if n is None:raise ValueError('Expected native arXiv control absent')
    foreground(device);v=bounds(n);device.tap((v[0]+v[2])//2,(v[1]+v[3])//2)
def wait(device,predicate,timeout=40):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(device)
        if predicate(ns):return ns
        time.sleep(.5)
    raise ValueError('Public paper data unavailable or expected screen changed')
def term(value):
    value=str(value).strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 -]{1,79}',value):raise ValueError('Use 2–80 plain ASCII search characters')
    return value

def paper(ns):
    titles=sorted([n for n in ns if n.get('resource-id')==PKG+':id/paper_title'],key=lambda n:bounds(n)[1])
    if not titles:raise ValueError('No exposed paper card')
    first=titles[0];low=bounds(first)[1];high=bounds(titles[1])[1] if len(titles)>1 else 2205
    fields={'title':'paper_title','authors':'paper_authors','submitted':'paper_published_date','arxiv_id':'paper_id','categories':'paper_categories','abstract':'paper_summary'};result={}
    for key,rid in fields.items():
        values=[n.get('text','') for n in ns if n.get('resource-id')==PKG+':id/'+rid and low<=bounds(n)[1] and bounds(n)[3]<=high and n.get('text')]
        if len(values)!=1:raise ValueError('First paper metadata/abstract is missing or ambiguous')
        result[key]=values[0]
    if not re.fullmatch(r'ID: \d{4}\.\d{4,5}v\d+',result['arxiv_id']) or len(result['abstract'])<80:raise ValueError('Expected a modern arXiv paper ID and exposed abstract')
    result['scope']='Native accessibility metadata and abstract; abstract can extend beyond visible viewport. Public untrusted research text, not full paper/PDF.'
    return result

def dashboard(ns):return find(ns,id='menu_search') is not None and find(ns,id='paper_title') is not None and find(ns,id='searchTextView') is None and find(ns,text='Donate') is None

def open_app(device,params,context):
    device.adb('shell','am','start','-W','-S','-n',ACT)
    for _ in range(30):
        focus=device.adb('shell','dumpsys window | grep -m1 mCurrentFocus')
        if 'DeprecatedTargetSdkVersionDialog' in focus:
            # System-owned compatibility notice: only Back, never Check for update.
            root=ET.fromstring(device.dump_xml(use_portal=False));texts={n.get('text','') for n in root.iter('node')}
            if 'arXiv eXplorer' not in texts or not any('built for an older version of Android' in t for t in texts):raise ValueError('Unexpected compatibility notice')
            device.adb('shell','input','keyevent','KEYCODE_BACK');continue
        if PKG+'/' in focus:break
        time.sleep(.1)
    else:raise ValueError('arXiv did not acquire native focus')
    ns=nodes(device)
    if find(ns,text='Donate') and find(ns,text='Consider donating to support the developer.'):
        tap(device,find(ns,text='NOT NOW'))
    ns=wait(device,dashboard)
    return {'screen':'dashboard','first_paper':paper(ns)}

def prepare_search(device,params,context):
    ns=nodes(device)
    if not find(ns,id='searchTextView'):
        if not dashboard(ns):raise ValueError('Public dashboard required before search')
        tap(device,find(ns,id='menu_search'));ns=wait(device,lambda ns:find(ns,id='searchTextView') is not None)
    n=find(ns,id='searchTextView')
    if n.get('class')!='android.widget.EditText':raise ValueError('Expected native search input')
    return {'screen':'paper_search','query':'' if n.get('text')==n.get('hint') else n.get('text','')}

def search(device,params,context):
    query=term(params['query']);open_app(device,{},context);old=paper(nodes(device))['arxiv_id'];prepare_search(device,{},context);ns=nodes(device);edit=find(ns,id='searchTextView')
    if edit.get('text') not in {'',edit.get('hint'),'Search for papers'}:raise ValueError('Expected empty native search field')
    tap(device,edit);foreground(device);device.adb('shell','input','text',input_text_arg(query));ns=nodes(device)
    if find(ns,id='searchTextView').get('text')!=query:raise ValueError('Native submitted query mismatch')
    foreground(device);device.press_enter()
    def changed(ns):
        if not dashboard(ns):return False
        try:return paper(ns)['arxiv_id']!=old
        except ValueError:return False
    return paper(wait(device,changed))
def read_paper(device,params,context):
    ns=nodes(device)
    if not dashboard(ns):raise ValueError('Public dashboard paper required')
    return paper(ns)
def dashboard_ok(device,context):
    try:return dashboard(nodes(device)) and context.result.get('first_paper')==read_paper(device,{},context)
    except ValueError:return False
def search_field_ok(device,context):
    try:
        ns=nodes(device);n=find(ns,id='searchTextView');return n is not None and n.get('class')=='android.widget.EditText' and context.result.get('screen')=='paper_search'
    except ValueError:return False
def paper_ok(device,context):
    try:return context.result==read_paper(device,{},context)
    except ValueError:return False
