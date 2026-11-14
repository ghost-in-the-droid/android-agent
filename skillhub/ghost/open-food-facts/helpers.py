"""Public name search and native nutrition labels; no camera or contributions."""
import re
import time
import xml.etree.ElementTree as ET
from gitd.bots.common.adb import input_text_arg
PKG='openfoodfacts.github.scrachx.openfood'

def foreground(device):
    if PKG+'/' not in device.adb('shell','dumpsys window | grep -m1 mCurrentFocus'):
        raise ValueError('Open Food Facts must own the focused window')

def bounds(n):return list(map(int,re.findall(r'\d+',n.get('bounds',''))))
def label(n):return n.get('content-desc') or n.get('text','')
def nodes(device):
    foreground(device);root=ET.fromstring(device.dump_xml());foreground(device)
    return [dict(n.attrib) for n in root.iter('node') if len(bounds(n))==4 and 0<=bounds(n)[0]<bounds(n)[2]<=1080 and 0<=bounds(n)[1]<bounds(n)[3]<=2205 and n.get('enabled')!='false']
def find(ns,text):return next((n for n in ns if label(n)==text),None)
def field(ns):return next((n for n in ns if n.get('class')=='android.widget.EditText'),None)
def tap(device,n):
    if n is None:raise ValueError('Expected public food control is missing')
    foreground(device);v=bounds(n);device.tap((v[0]+v[2])//2,(v[1]+v[3])//2)
def wait(device,predicate,timeout=35):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(device)
        if predicate(ns):return ns
        time.sleep(.4)
    raise ValueError('Public food data unavailable or expected screen changed')
def term(value):
    value=str(value).strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 -]{1,59}',value):raise ValueError('Use a 2–60 character public product name')
    return value

def cards(ns):
    if not field(ns) or not any(re.fullmatch(r'\d+ products \(United States\)',label(n)) for n in ns):return []
    result=[]
    for n in ns:
        if n.get('class')!='android.view.View' or not re.match(r'^(?:\d+%|N/A) ',label(n)) or bounds(n)[0]!=0 or bounds(n)[2]!=1080:continue
        scores=[label(s) for s in ns if s.get('class')=='android.widget.ImageView' and ('Nutri-Score' in label(s)) and bounds(n)[1]<=bounds(s)[1]<bounds(s)[3]<=bounds(n)[3]]
        if len(scores)==1:result.append({'label':label(n),'nutri_score':scores[0],'_node':n})
    return result

def results(ns):
    cs=cards(ns)
    if not cs:raise ValueError('Complete United States search cards with Nutri-Score labels required')
    return {'query':field(ns).get('text',''),'country':'United States','products':[{k:v for k,v in c.items() if k!='_node'} for c in cs],'scope':'Complete visible cards only; public community data, not dietary advice.'}

def product(ns):
    if not find(ns,'Nutrient levels') or field(ns):raise ValueError('Product overview required')
    titles=[label(n) for n in ns if n.get('class')=='android.view.View' and bounds(n)[0]>=300 and 238<bounds(n)[1]<370 and label(n)]
    scores=[label(n) for n in ns if n.get('class')=='android.widget.Button' and re.match(r'^Nutri-Score [A-E] \(',label(n)) and bounds(n)[1]<1000]
    if len(titles)!=1 or len(scores)!=1:raise ValueError('Complete product title and Nutri-Score required')
    quantity=[label(n) for n in ns if n.get('class')=='android.view.View' and bounds(n)[0]>=300 and 465<=bounds(n)[1]<560 and label(n)]
    return {'product':titles[0],'nutri_score':scores[0],'quantity':quantity}

def nutrients(ns):
    head=next((label(n) for n in ns if label(n).startswith('Details for Nutrient levels with ')),None)
    rows=[label(n) for n in ns if n.get('class')=='android.widget.Button' and re.fullmatch(r'(?:Fat|Saturated fat|Sugars|Salt) in (?:high|moderate|low) quantity \([\d.]+%\)',label(n))]
    if not head or len(rows)!=4:raise ValueError('Four complete native nutrient-level rows required')
    return {'heading':head,'nutrient_levels':rows,'scope':'Literal visible community product labels; no nutrition advice.'}

def open_app(device,params,context):
    device.adb('shell','am','start','-W','-S','-n',PKG+'/org.openfoodfacts.app.MainActivity')
    for _ in range(12):
        ns=nodes(device)
        if field(ns) and find(ns,'Search'):return {'screen':'search','query':field(ns).get('text','')}
        if find(ns,'Search for a product'):tap(device,find(ns,'Search for a product'));continue
        if find(ns,'Camera access') and find(ns,'Later'):tap(device,find(ns,'Later'));continue
        if find(ns,'Continue') and any('Welcome' in label(n) for n in ns):tap(device,find(ns,'Continue'));continue
        welcome=any(any(s in label(n) for s in ('Please choose a country:','Choose foods that are good','See the food data relevant')) for n in ns)
        if find(ns,'Next') and welcome:tap(device,find(ns,'Next'));continue
        raise ValueError('Unexpected onboarding or screen; camera/account access refused')
    raise ValueError('Onboarding did not reach public name search')

def search(device,params,context):
    query=term(params['query']);open_app(device,{},context);ns=nodes(device)
    if field(ns).get('text'):raise ValueError('Use a clean empty search field')
    tap(device,field(ns));foreground(device);device.adb('shell','input','text',input_text_arg(query));foreground(device);device.press_enter()
    ns=wait(device,lambda ns:bool(cards(ns)))
    if field(ns).get('text','').lower()!=query.lower():raise ValueError('Submitted product query does not match')
    return results(ns)
def read_results(device,params,context):return results(nodes(device))
def open_product(device,params,context):
    ns=nodes(device);cs=cards(ns);index=int(params['index'])
    if index<0 or index>=len(cs):raise ValueError('Index must identify a complete visible card')
    tap(device,cs[index]['_node']);ns=wait(device,lambda ns:find(ns,'Nutrient levels') is not None)
    return product(ns)
def read_nutrients(device,params,context):
    ns=nodes(device)
    if not any(label(n).startswith('Details for Nutrient levels with ') for n in ns):
        product(ns);tap(device,find(ns,'Nutrient levels'));ns=wait(device,lambda ns:any(label(n).startswith('Details for Nutrient levels with ') for n in ns))
    return nutrients(ns)
def back_to_results(device,params,context):
    ns=nodes(device)
    if any(label(n).startswith('Details for Nutrient levels with ') for n in ns):
        nutrients(ns);tap(device,find(ns,'Back'));ns=wait(device,lambda ns:find(ns,'Nutrient levels') is not None)
    product(ns);tap(device,find(ns,'Back'));return results(wait(device,lambda ns:bool(cards(ns))))

def search_ok(device,context):
    try:
        ns=nodes(device);return field(ns) is not None and find(ns,'Search') is not None and context.result.get('screen')=='search'
    except ValueError:return False
def results_ok(device,context):
    try:return context.result==read_results(device,{},context)
    except ValueError:return False
def product_ok(device,context):
    try:return context.result==product(nodes(device))
    except ValueError:return False
def nutrients_ok(device,context):
    try:return context.result==nutrients(nodes(device))
    except ValueError:return False
