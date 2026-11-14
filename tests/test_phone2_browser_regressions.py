"""Chrome private-mode selectors must come from browser UI, never page text."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def chrome():
    spec = importlib.util.spec_from_file_location('chrome', ROOT / 'skillhub/ghost/chrome/helpers.py')
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    return h


@pytest.mark.parametrize('resource', ['location_bar_incognito_badge', 'new_tab_incognito_title', 'new_tab_incognito_icon'])
def test_chrome_recognizes_old_and_current_private_tab_resources(monkeypatch, resource):
    h = chrome()
    nodes = [{'id': h._ID + resource, 'text': '', 'cls': 'android.widget.ImageView'}]
    monkeypatch.setattr(h, 'visible_nodes', lambda _: nodes)
    result = h.wait_for_incognito(None, {}, None)
    assert result['success']
    assert result['data']['incognito']
    assert h.incognito_open(None, SimpleNamespace(result={}))


def test_chrome_webpage_cannot_prove_private_mode(monkeypatch):
    h = chrome()
    nodes = [{'id': 'page:id/new_tab_incognito_title', 'text': "You've gone Incognito", 'cls': 'android.webkit.WebView'}]
    monkeypatch.setattr(h, 'visible_nodes', lambda _: nodes)
    assert not h.page_info(None)['incognito']
    assert not h.incognito_open(None, SimpleNamespace(result={}))

def test_chrome_rejects_non_web_url_before_device_input():
    h=chrome()
    for url in ['javascript:alert(1)','file:///private','https://example.org/with space']:
        assert not h.open_url(object(),{'url':url,'incognito':True},None)['success']


def test_chrome_native_host_and_private_mode_are_required(monkeypatch):
    h=chrome();ctx=SimpleNamespace(params={'url':'https://example.org','incognito':True},result={})
    monkeypatch.setattr(h,'page_info',lambda _:{'url':'example.org.evil.invalid','title':'Example','incognito':True})
    assert not h.url_matches(None,ctx)
    monkeypatch.setattr(h,'page_info',lambda _:{'url':'example.org/','title':'Example','incognito':False})
    assert not h.url_matches(None,ctx)
    monkeypatch.setattr(h,'page_info',lambda _:{'url':'example.org/','title':'Example','incognito':True})
    assert h.url_matches(None,ctx)


def test_chrome_resume_preserves_already_visible_tab_model():
    h=chrome()
    class D:
        def adb(self,*args):
            assert args==('shell','dumpsys','window'), 'Visible Chrome must not be relaunched into another tab model'
            return 'mCurrentFocus=Window{x u0 com.android.chrome/.ChromeTabbedActivity}'
    assert h.resume_chrome(D(),{},None)['success']


def test_private_entry_launches_incognito_directly(monkeypatch):
    h=chrome();commands=[]
    d=SimpleNamespace(adb=lambda *args:commands.append(args))
    monkeypatch.setattr(h,'wait_for_incognito',lambda *_:{'success':True,'data':{'incognito':True}})
    assert h.open_private_tab(d,{},None)['success']
    assert len(commands)==1 and 'IncognitoTabLauncher' in commands[0][-1] and '-W' in commands[0]


@pytest.mark.parametrize('private', [True, False])
def test_loaded_page_mode_uses_native_current_tab_grid_and_restores_same_page(monkeypatch, private):
 h=chrome()
 initial=[{'id':h._ID+'tab_switcher_button','bounds':(810,80,945,238),'text':''}]
 grid=[{'id':h._ID+'tab_switcher_view_holder','text':''},
       {'id':h._ID+'search_box_text','text':'Search your Incognito tabs' if private else 'Search your tabs'}]
 restored=[{'id':h._ID+'url_bar','text':'example.org'}]
 screens=iter([grid,restored]);monkeypatch.setattr(h,'visible_nodes',lambda _:next(screens))
 monkeypatch.setattr(h,'chrome_foreground',lambda _:True)
 calls=[]
 d=SimpleNamespace(tap=lambda x,y:calls.append('tab grid'),back=lambda:calls.append('back'))
 assert h.private_tab_grid_evidence(d,initial,'example.org') is private
 assert calls==['tab grid','back']


def test_webpage_text_cannot_substitute_for_native_tab_grid_private_label(monkeypatch):
 h=chrome();initial=[{'id':h._ID+'tab_switcher_button','bounds':(810,80,945,238),'text':''}]
 grid=[{'id':h._ID+'tab_switcher_view_holder','text':''},
       {'id':'webpage:fake','text':'Search your Incognito tabs'}]
 restored=[{'id':h._ID+'url_bar','text':'example.org'}]
 screens=iter([grid,restored]);monkeypatch.setattr(h,'visible_nodes',lambda _:next(screens))
 monkeypatch.setattr(h,'chrome_foreground',lambda _:True)
 d=SimpleNamespace(tap=lambda *args:None,back=lambda:None)
 assert not h.private_tab_grid_evidence(d,initial,'example.org')
