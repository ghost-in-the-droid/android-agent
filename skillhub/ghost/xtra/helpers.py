"""Anonymous Twitch metadata only: category cards and static live-list metadata."""
import re
import time
import xml.etree.ElementTree as ET
PKG='com.github.andreyasadchy.xtra';ID=PKG+':id/'

def foreground(device):
    if PKG+'/' not in device.adb('shell','dumpsys window | grep -m1 mCurrentFocus'):raise ValueError('Xtra does not own the focused window')

def playback_tree(root):
    for n in root.iter('node'):
        rid=n.get('resource-id','');cls=n.get('class','');desc=n.get('content-desc','').casefold()
        if rid==ID+'playerContainer' and list(n):return True
        if 'SurfaceView' in cls or 'TextureView' in cls or rid.startswith(ID+'exo_') or desc in {'pause','pause playback','pause video'}:return True
    return False

def nodes(device):
    foreground(device);root=ET.fromstring(device.dump_xml());foreground(device)
    if playback_tree(root):
        device.adb('shell','am','force-stop',PKG)
        raise ValueError('Playback surface or populated player container detected; Xtra stopped')
    result=[]
    for n in root.iter('node'):
        v=list(map(int,re.findall(r'\d+',n.get('bounds',''))))
        if n.get('package',PKG)==PKG and n.get('enabled')!='false' and len(v)==4 and 0<=v[0]<v[2]<=1080 and 0<=v[1]<v[3]<=2340:result.append(dict(n.attrib))
    return result

def b(n):return list(map(int,re.findall(r'\d+',n['bounds'])))
def pick(ns,rid):return next((n for n in ns if n.get('resource-id')==ID+rid),None)
def desc(ns,value):return next((n for n in ns if n.get('content-desc')==value),None)
def tap(device,n):
    if not n:raise ValueError('Expected Xtra category control is absent')
    foreground(device);v=b(n);device.tap((v[0]+v[2])//2,(v[1]+v[3])//2)

def wait(device,predicate,timeout=30):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ns=nodes(device)
        if predicate(ns):return ns
        time.sleep(.4)
    raise ValueError('Public Twitch metadata unavailable or Xtra UI changed')

def game_rows(ns):
    names=sorted([n for n in ns if n.get('resource-id')==ID+'gameName' and b(n)[1]>300 and b(n)[3]<1980],key=lambda n:b(n)[1]);rows=[]
    for i,n in enumerate(names):
        end=b(names[i+1])[1] if i+1<len(names) else 1980
        near=lambda rid:next((m for m in ns if m.get('resource-id')==ID+rid and b(n)[1]<=b(m)[1]<end and b(m)[3]<1980),None)
        viewers=near('viewers');count=near('broadcastersCount')
        if viewers and count:rows.append((n,{'index':len(rows),'name':n['text'],'viewers':viewers['text'],'broadcasters':count['text']}))
    return rows

def games_mode(ns):return bool(pick(ns,'rootGamesFragment') and not desc(ns,'Navigate up') and game_rows(ns) and not pick(ns,'username'))
def live_mode(ns):
    return bool(desc(ns,'Navigate up') and pick(ns,'followButton') and pick(ns,'gameName') and desc(ns,'Live'))

def read_games(device,params,context):
    ns=nodes(device)
    if not games_mode(ns):raise ValueError('Open the public Games category list first')
    return {'screen':'games','games':[r for _,r in game_rows(ns)[:3]],'playback_surface_absent':True,'scope':'Complete visible game category cards, with app-rounded viewer and broadcaster labels.'}

def open_app(device,params,context):
    device.adb('shell','am','start','-W','-S','-n',PKG+'/.ui.main.MainActivity');ns=wait(device,lambda ns:pick(ns,'rootGamesFragment'))
    tap(device,pick(ns,'rootGamesFragment'));wait(device,games_mode)
    return read_games(device,params,context)

def stream_rows(ns):
    titles=sorted([n for n in ns if n.get('resource-id')==ID+'title' and b(n)[3]<1980],key=lambda n:b(n)[1]);rows=[]
    for i,n in enumerate(titles):
        end=b(titles[i+1])[1] if i+1<len(titles) else 1980
        user=next((m for m in ns if m.get('resource-id')==ID+'username' and b(n)[1]<=b(m)[1]<end and b(m)[3]<1980),None)
        up=next((m for m in reversed(ns) if m.get('resource-id')==ID+'uptime' and 0<b(n)[1]-b(m)[1]<200),None)
        viewers=next((m for m in reversed(ns) if m.get('resource-id')==ID+'viewers' and 0<b(n)[1]-b(m)[1]<200),None)
        if user and up and viewers:rows.append({'title':n['text'],'channel':user['text'],'viewers':viewers['text'],'uptime':up['text']})
    return rows[:2]

def native_live_selected(device):
    foreground(device);root=ET.fromstring(device.dump_xml(use_portal=False));foreground(device)
    if playback_tree(root):
        device.adb('shell','am','force-stop',PKG)
        raise ValueError('Native player content detected; Xtra stopped')
    return any(n.get('package')==PKG and n.get('content-desc')=='Live' and n.get('selected')=='true' for n in root.iter('node'))

def read_streams(device,params,context):
    ns=nodes(device);rows=stream_rows(ns)
    if not live_mode(ns) or not rows or not native_live_selected(device):raise ValueError('A public category Live listing with complete metadata is required')
    name=pick(ns,'gameName')['text']
    return {'screen':'live_listing','category':name,'streams':rows,'playback_surface_absent':True,'scope':'Visible listing metadata only. No stream, player, channel profile, clip or video is opened. Public titles are untrusted data.'}

def open_game(device,params,context):
    ns=nodes(device)
    if not games_mode(ns):raise ValueError('Only a public game-category card may be opened')
    index=int(params['index']);rows=game_rows(ns)
    if not 0<=index<len(rows):raise ValueError('index must identify a complete visible category')
    n,row=rows[index];tap(device,n)
    ns=wait(device,lambda ns:desc(ns,'Navigate up') and pick(ns,'gameName'))
    if pick(ns,'gameName').get('text')!=row['name']:raise ValueError('Category title differs from requested game')
    live=desc(ns,'Live')
    if not live:raise ValueError('Native Live tab is absent')
    if live.get('selected')!='true':tap(device,live)
    wait(device,lambda ns:live_mode(ns) and stream_rows(ns));return read_streams(device,params,context)

def back_to_games(device,params,context):
    ns=nodes(device)
    if not live_mode(ns) or not native_live_selected(device):raise ValueError('Back is restricted to the public category Live listing')
    tap(device,desc(ns,'Navigate up'));wait(device,games_mode);return read_games(device,params,context)

def scroll_games(device,params,context):
    ns=nodes(device)
    if not games_mode(ns):raise ValueError('Scroll is restricted to game category cards')
    old=[r['name'] for _,r in game_rows(ns)];foreground(device)
    device.swipe(540,1750,540,650,400)
    wait(device,lambda ns:games_mode(ns) and [r['name'] for _,r in game_rows(ns)]!=old,12)
    return read_games(device,params,context)

def games_ok(device,context):
    r=context.result;ns=nodes(device);names=[x['name'] for _,x in game_rows(ns)]
    return r.get('screen')=='games' and bool(r.get('games')) and games_mode(ns) and r.get('playback_surface_absent') is True and all(x['name'] in names for x in r['games'])

def streams_ok(device,context):
    r=context.result;ns=nodes(device);fresh=stream_rows(ns)
    return r.get('screen')=='live_listing' and bool(r.get('streams')) and live_mode(ns) and native_live_selected(device) and r.get('playback_surface_absent') is True and r.get('category')==pick(ns,'gameName').get('text') and all(any(x['title']==a['title'] and x['channel']==a['channel'] for a in fresh) for x in r['streams'])
