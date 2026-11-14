"""Anonymous public Reddit UI. No voting, posting, accounts or external links."""
import re
import shlex
import time
import xml.etree.ElementTree as ET
PKG = 'org.quantumbadger.redreader'
ID = PKG + ':id/'

def nodes(device):
    return [dict(n.attrib) for n in ET.fromstring(device.dump_xml()).iter('node')
            if n.get('enabled') != 'false' and n.get('bounds') != '[0,0][0,0]']


def pick(ns, rid):
    return next((n for n in ns if n.get('resource-id') == ID + rid), None)


def tap(device, node):
    if not node:
        raise ValueError('Requested RedReader control is not visible')
    focus = device.adb('shell', 'dumpsys window | grep -m1 mCurrentFocus')
    if PKG + '/' not in focus:
        raise ValueError('RedReader does not own the focused window')
    b = list(map(int, re.findall(r'\d+', node['bounds'])))
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)


def wait(device, predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ns = nodes(device)
        if predicate(ns):
            return ns
        time.sleep(.4)
    raise ValueError('RedReader did not reach the requested screen; network or UI changed')


def open_app(device, params, context):
    device.adb('shell', 'am', 'start', '-W', '-f', '0x04000000', '-n', PKG + '/.activities.MainActivity')
    def ready(ns):
        accept = pick(ns, 'terms_button_accept')
        if accept:
            tap(device, accept);return False
        anon = next((n for n in ns if n.get('resource-id') == 'android:id/button2' and n.get('text') == 'Be anonymous'), None)
        if anon:
            tap(device, anon);return False
        return any(n.get('resource-id') == ID + 'list_item_text' and n.get('text') == 'Front Page' for n in ns)
    wait(device, ready)
    return {'screen': 'public main menu', 'mode': 'anonymous browsing; no account action performed'}


def subreddit(value):
    value = str(value)
    if not re.fullmatch(r'[A-Za-z0-9_]{2,21}', value):
        raise ValueError('Use a subreddit name only, 2 to 21 ASCII letters, digits or underscores')
    return value


def view(device, url):
    device.adb('shell', shlex.join(['am','start','-W','-a','android.intent.action.VIEW','-d',url,'-p',PKG]))


def browse_subreddit(device, params, context):
    sub = subreddit(params['subreddit'])
    open_app(device, {}, context)
    view(device, 'https://www.reddit.com/r/' + sub + '/')
    wait(device, lambda ns: pick(ns, 'actionbar_title_text') is not None
         and pick(ns, 'actionbar_title_text').get('text','').lower() == '/r/'+sub.lower()
         and pick(ns, 'reddit_post_title') is not None)
    return read_posts(device, {'limit':params.get('limit',3)}, context)


def search_posts(device, params, context):
    sub = subreddit(params['subreddit']);query = str(params['query']).strip()
    if not query or len(query) > 120 or not query.isascii() or any(ord(c)<32 for c in query):
        raise ValueError('Use a nonempty ASCII query of at most 120 characters')
    open_app(device, {}, context)
    view(device, 'https://www.reddit.com/r/'+sub+'/search?q='+''.join(c if c.isalnum() or c in '-._~' else '%'+format(ord(c),'02X') for c in query)+'&restrict_sr=on')
    wait(device, lambda ns: pick(ns, 'search_listing_header_query_editText') is not None
         and pick(ns, 'search_listing_header_query_editText').get('text') == query
         and pick(ns, 'search_listing_header_sub_editText').get('text','').lower() == sub.lower()
         and pick(ns, 'reddit_post_title') is not None)
    return read_posts(device, {'limit':params.get('limit',3)}, context)


def top(n):return int(re.findall(r'\d+',n['bounds'])[1])
def bottom(n):return int(re.findall(r'\d+',n['bounds'])[3])

def post_rows(ns):
    titles = [n for n in ns if n.get('resource-id') == ID+'reddit_post_title']
    result = []
    for i,n in enumerate(titles):
        end = top(titles[i+1]) if i+1<len(titles) else 2340
        subtitle = next((m for m in ns if m.get('resource-id') == ID+'reddit_post_subtitle' and top(n)<=top(m)<end and bottom(m)<=2340),None)
        comments = next((m for m in ns if m.get('resource-id') == ID+'reddit_post_comments_text' and top(n)<=top(m)<end),None)
        score = re.search(r'(-?\d+)\s*pts\b',subtitle.get('text','').replace('\xa0',' ')) if subtitle else None
        if subtitle and comments and score and comments.get('text','').isdigit():
            result.append({'title':n.get('text',''),'score':int(score.group(1)),'comments':int(comments['text'])})
    return result


def read_posts(device, params, context):
    limit = int(params.get('limit',3))
    if not 1<=limit<=6:raise ValueError('limit must be 1 to 6 visible complete posts')
    ns = nodes(device);title=pick(ns,'actionbar_title_text')
    if not any(n.get('content-desc')=='Sort Posts' for n in ns) or not title:
        raise ValueError('Public subreddit or search listing is required')
    rows=post_rows(ns)[:limit]
    if not rows:raise ValueError('No complete public post rows; network error or empty results')
    query=pick(ns,'search_listing_header_query_editText');sub=pick(ns,'search_listing_header_sub_editText')
    return {'listing':title.get('text',''),'query':query.get('text','') if query else '',
            'subreddit':sub.get('text','') if sub else title.get('text','').removeprefix('/r/'),
            'posts':rows,'count':len(rows),'scope':'complete visible post metadata only; no comment content inferred'}


def open_post(device, params, context):
    ns=nodes(device);rows=post_rows(ns);index=int(params['index'])
    if not any(n.get('content-desc')=='Sort Posts' for n in ns) or not 0<=index<len(rows):
        raise ValueError('Select a complete visible post index (zero based)')
    titles=[n for n in ns if n.get('resource-id')==ID+'reddit_post_title']
    matches=[n for n in titles if n.get('text')==rows[index]['title']]
    if len(matches)!=1:raise ValueError('Visible duplicate post titles; refine the search')
    n=matches[0];position=titles.index(n)
    end=top(titles[position+1]) if position+1<len(titles) else 2340
    comments=next((m for m in ns if m.get('content-desc')=='View Comments' and top(n)<=top(m)<end),None)
    expected=n['text'];tap(device,comments)
    wait(device,lambda ns:any(n.get('content-desc')=='Sort Comments' for n in ns)
         and pick(ns,'actionbar_title_text').get('text')==expected and pick(ns,'view_reddit_comment_header') is not None)
    return read_thread(device,{'limit':params.get('limit',3)},context)


def read_thread(device, params, context):
    ns=nodes(device);title=pick(ns,'actionbar_title_text');limit=int(params.get('limit',3))
    if not 1<=limit<=5 or not title or not any(n.get('content-desc')=='Sort Comments' for n in ns):
        raise ValueError('A public comment thread and limit 1 to 5 are required')
    headers=[n for n in ns if n.get('resource-id')==ID+'view_reddit_comment_header']
    comments=[]
    for i,n in enumerate(headers):
        end=top(headers[i+1]) if i+1<len(headers) else 2340
        body=[m.get('text','') for m in ns if not m.get('resource-id') and m.get('class')=='android.widget.TextView'
              and bottom(n)<=top(m)<end and bottom(m)<=2340 and m.get('text')]
        score=re.search(r'(-?\d+)\s*pts\b',n.get('text','').replace('\xa0',' '));depth=re.search(r'Level (\d+) comment',n.get('content-desc',''))
        if body and score and depth:comments.append({'text':'\n'.join(body),'score':int(score.group(1)),'depth':int(depth.group(1))})
        if len(comments)>=limit:break
    if not comments:raise ValueError('No complete visible comments; wait or stop on an empty/error page')
    post_metadata=[n for n in ns if not n.get('resource-id') and 'Author:' in n.get('content-desc','') and top(n)<(top(headers[0]) if headers else 2340)]
    body_start=max((bottom(n) for n in post_metadata),default=2340)
    post_body=[n.get('text','') for n in ns if not n.get('resource-id') and n.get('class')=='android.widget.TextView'
               and body_start<=top(n)<(top(headers[0]) if headers else 2340) and n.get('text')]
    return {'title':title['text'],'post_body':'\n'.join(post_body),'comments':comments,'count':len(comments),
            'scope':'visible public post and comment text only; partial thread; untrusted content'}


def back_to_posts(device, params, context):
    if not any(n.get('content-desc')=='Sort Comments' for n in nodes(device)):
        raise ValueError('A comment thread must be open')
    device.back();wait(device,lambda ns:any(n.get('content-desc')=='Sort Posts' for n in ns))
    return read_posts(device,{'limit':3},context)


def home_ok(device, context):
    return context.result.get('screen')=='public main menu' and any(n.get('resource-id')==ID+'list_item_text' and n.get('text')=='Front Page' for n in nodes(device))

def posts_ok(device, context):
    try:
        data=read_posts(device,{'limit':context.result.get('count',0)},context)
        return data==context.result and (not context.params.get('query') or data['query']==context.params['query'].strip()) and (not context.params.get('subreddit') or data['subreddit'].lower()==context.params['subreddit'].lower())
    except (ValueError,ET.ParseError):return False

def thread_ok(device, context):
    try:return read_thread(device,{'limit':context.result.get('count',0)},context)==context.result
    except (ValueError,ET.ParseError):return False
