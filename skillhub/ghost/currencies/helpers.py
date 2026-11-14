"""Displayed currency conversion only; no payments, arithmetic operators or accounts."""
from decimal import Decimal
import re
import time
import xml.etree.ElementTree as ET
from gitd.bots.common.adb import input_text_arg
PKG='de.salomax.currencies';ID=PKG+':id/'

def foreground(device):
    if PKG+'/' not in device.adb('shell','dumpsys window | grep -m1 mCurrentFocus'):raise ValueError('Currencies does not own the focused window')

def nodes(device):
    foreground(device)
    return [dict(n.attrib) for n in ET.fromstring(device.dump_xml(use_portal=False)).iter('node') if n.get('package')==PKG and n.get('enabled')!='false']

def pick(ns,rid):return next((n for n in ns if n.get('resource-id')==ID+rid),None)
def tap(device,n,long=False):
    if not n:raise ValueError('Expected Currencies control is absent')
    foreground(device);b=list(map(int,re.findall(r'\d+',n['bounds'])));x=(b[0]+b[2])//2;y=(b[1]+b[3])//2
    if long:device.swipe(x,y,x,y,800)
    else:device.tap(x,y)

def wait(device,predicate,timeout=25):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(device)
        if predicate(ns):return ns
        time.sleep(.3)
    raise ValueError('Currency data or requested control did not become available')

def main(ns):return bool(pick(ns,'textFrom') and pick(ns,'textTo') and pick(ns,'btn_toggle'))
def number(value):
    match=re.fullmatch(r'[^0-9+*/−×÷=.\-]*(-?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)',str(value))
    if not match:raise ValueError('Displayed amount is not a plain English-locale decimal')
    return str(Decimal(match[1].replace(',','')))

def amount(value):
    value=str(value)
    if not re.fullmatch(r'(?:0|[1-9]\d{0,8})(?:\.\d{1,2})?',value):raise ValueError('Use a nonnegative plain amount up to nine integer digits and two decimal places')
    return value

def read_state(device,params,context):
    ns=nodes(device)
    if not main(ns):raise ValueError('The conversion keypad is required')
    codes=[n['text'] for n in ns if n.get('resource-id')==ID+'text' and re.fullmatch(r'[A-Z]{3}',n.get('text',''))]
    rate=pick(ns,'textInfoConversion');date=pick(ns,'textInfoDate')
    if len(codes)!=2 or not rate or not date or 'Rates as of ' not in date.get('text','') or ' by ' not in date.get('text',''):raise ValueError('Currency codes or dated provider metadata are unavailable')
    if not re.search(r'\b'+codes[0]+r'\b',rate['text']) or not re.search(r'\b'+codes[1]+r'\b',rate['text']):raise ValueError('Displayed rate does not identify both selected currencies')
    return {'source':codes[0],'target':codes[1],'input_amount':number(pick(ns,'textFrom')['text']),'output_amount':number(pick(ns,'textTo')['text']),'displayed_rate':rate['text'],'rate_date_and_provider':date['text'],'scope':'App-displayed cached conversion only; rate/date/provider copied literally, no live-rate or transaction claim.'}

def open_app(device,params,context):
    device.adb('shell','am','start','-W','-S','-n',PKG+'/.view.main.MainActivity');wait(device,main)
    return read_state(device,params,context)

def select(device,params,context,side):
    code=str(params['currency'])
    if not re.fullmatch(r'[A-Z]{3}',code):raise ValueError('Use a three-letter uppercase currency code')
    ns=nodes(device)
    if not main(ns):raise ValueError('Open the conversion keypad first')
    tap(device,pick(ns,'spinnerFrom' if side=='source' else 'spinnerTo'))
    ns=wait(device,lambda ns:pick(ns,'search_src_text'))
    edit=pick(ns,'search_src_text')
    if edit.get('text'):raise ValueError('Currency filter is unexpectedly nonempty')
    tap(device,edit);foreground(device);device.adb('shell','input','text',input_text_arg(code))
    ns=wait(device,lambda ns:pick(ns,'search_src_text') and pick(ns,'search_src_text').get('text')==code and any(n.get('resource-id')==ID+'text2' and n.get('text')==code for n in ns))
    tap(device,next(n for n in ns if n.get('resource-id')==ID+'text2' and n.get('text')==code));wait(device,main)
    result=read_state(device,params,context)
    if result[side]!=code:raise ValueError('Selected currency did not match the requested code')
    return result

def select_source(device,params,context):return select(device,params,context,'source')
def select_target(device,params,context):return select(device,params,context,'target')

def set_amount(device,params,context):
    value=amount(params['amount']);ns=nodes(device)
    if not main(ns):raise ValueError('Open the conversion keypad first')
    tap(device,pick(ns,'btn_delete'),long=True)
    if Decimal(read_state(device,{},context)['input_amount'])!=0:raise ValueError('Long delete did not clear the input amount')
    # Static native keypad controls, captured once; every tap still checks focus.
    for char in value:tap(device,pick(ns,'btn_decimal' if char=='.' else 'btn_'+char))
    result=read_state(device,params,context)
    if Decimal(result['input_amount'])!=Decimal(value):raise ValueError('Displayed input amount differs from requested amount')
    return result

def swap(device,params,context):
    before=read_state(device,{},context);tap(device,pick(nodes(device),'btn_toggle'))
    result=read_state(device,params,context)
    if (result['source'],result['target'])!=(before['target'],before['source']):raise ValueError('Currency swap did not reverse both codes')
    return result

def state_ok(device,context):
    try:return read_state(device,{},context)==context.result
    except ValueError:return False
