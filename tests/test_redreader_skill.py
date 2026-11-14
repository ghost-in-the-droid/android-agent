import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
spec=importlib.util.spec_from_file_location('redreader_helpers',Path(__file__).parents[1]/'skillhub/ghost/redreader/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

def node(rid='',text='',top=0,desc='',bottom=None):return {'resource-id':h.ID+rid if rid else '', 'text':text,'content-desc':desc,'bounds':f'[0,{top}][100,{bottom or top+40}]','class':'android.widget.TextView'}
def listing():
 return [node('actionbar_title_text','Search for "solar" on /r/askscience',80),node(desc='Sort Posts',top=80),node('search_listing_header_query_editText','solar',270),node('search_listing_header_sub_editText','askscience',476),node('reddit_post_title','Public solar question',850),node('reddit_post_subtitle','1 pts by Someone',920,desc='1 up votes.\nAuthor: someone.\n'),node('reddit_post_comments_text','12',954),node(desc='View Comments',top=880)]

def test_subreddit_path_injection_rejected():
 for value in ['../user/private','science?x=1','science/path','a','x'*22]:
  with pytest.raises(ValueError):h.subreddit(value)

def test_post_metadata_omits_author_and_requires_complete_row():
 ns=listing()+[node('reddit_post_title','Incomplete last row',2310)]
 assert h.post_rows(ns)==[{'title':'Public solar question','score':1,'comments':12}]

def test_validator_checks_query_subreddit_and_current_metadata(monkeypatch):
 ns=listing();monkeypatch.setattr(h,'nodes',lambda _:ns);data=h.read_posts(None,{'limit':3},None)
 assert h.posts_ok(None,SimpleNamespace(params={'query':'solar','subreddit':'askscience'},result=data))
 assert not h.posts_ok(None,SimpleNamespace(params={'query':'wind'},result=data))
 assert not h.posts_ok(None,SimpleNamespace(params={'subreddit':'other'},result=data))
 data['posts'][0]['score']=999
 assert not h.posts_ok(None,SimpleNamespace(params={},result=data))

def test_open_post_uses_comments_instead_of_external_title_link(monkeypatch):
 ns=listing();calls=[];monkeypatch.setattr(h,'nodes',lambda _:ns);monkeypatch.setattr(h,'tap',lambda d,n:calls.append(n));monkeypatch.setattr(h,'wait',lambda *_:None);monkeypatch.setattr(h,'read_thread',lambda *_:{'title':'Public solar question'})
 h.open_post(None,{'index':0},None)
 assert len(calls)==1 and calls[0]['content-desc']=='View Comments'

def test_no_comments_never_claims_thread_summary(monkeypatch):
 monkeypatch.setattr(h,'nodes',lambda _:[node('actionbar_title_text','Post',80),node(desc='Sort Comments',top=80)])
 with pytest.raises(ValueError,match='No complete visible comments'):h.read_thread(None,{},None)

def test_negative_displayed_scores_are_not_flipped_positive():
 ns=listing();ns[5]['text']='-7\xa0pts by Someone';ns[5]['content-desc']='7 down votes.'
 assert h.post_rows(ns)[0]['score']==-7
