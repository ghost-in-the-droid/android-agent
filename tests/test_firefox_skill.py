import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
s=importlib.util.spec_from_file_location('firefox_helpers',Path(__file__).parents[1]/'skillhub/ghost/firefox/helpers.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)

def test_public_landing_urls_exclude_local_credentials_and_account_flows():
 for url in ['http://example.org','https://127.0.0.1','https://localhost','https://demo.local','https://u:p@example.org','https://example.org:443','https://example.org/login','https://example.org/account/profile','https://example.org?q=private','https://example.org/#x','https://example.org/with space']:
  with pytest.raises(ValueError):h.safe_url(url)
 assert h.safe_url('https://example.org')=='https://example.org'
 assert h.safe_url('https://en.wikipedia.org/wiki/Solar_panel').endswith('Solar_panel')

def test_invalid_url_never_opens_browser():
 with pytest.raises(ValueError):h.open_url(object(),{'url':'https://example.org/login'},None)

def test_foreign_window_never_receives_tap():
 class D:
  def adb(self,*_):return 'mCurrentFocus=Window{x u0 com.android.systemui/.Shade}'
  def tap(self,*_):pytest.fail('Foreign tap')
 with pytest.raises(ValueError,match='focused window'):h.tap(D(),{'bounds':'[0,0][20,20]'})

def test_snapshot_only_returns_page_nodes_in_viewport():
 class D:
  def dump_xml(self):return '<hierarchy><node text="Toolbar secret" bounds="[0,0][100,10]"/><node class="android.webkit.WebView" text="Example" bounds="[0,10][100,100]"><node text="Visible" bounds="[0,20][100,40]"/><node text="Below" bounds="[0,110][100,130]"/></node></hierarchy>'
 d=h.snapshot(D());assert d['title']=='Example' and d['visible_text']==['Visible']


def test_find_validator_rejects_changed_query_or_counts(monkeypatch):
 result={'query':'docs','current_match':1,'total_matches':2,'scope':'native'}
 monkeypatch.setattr(h,'find_state',lambda _:dict(result))
 assert h.find_ok(None,SimpleNamespace(result=dict(result),params={'query':'docs'}))
 assert not h.find_ok(None,SimpleNamespace(result=dict(result),params={'query':'other'}))
 assert not h.find_ok(None,SimpleNamespace(result={**result,'total_matches':3},params={'query':'docs'}))

def test_page_validator_rejects_changed_page_text(monkeypatch):
 monkeypatch.setattr(h,'snapshot',lambda _:{'title':'Example','visible_text':['Visible'],'scope':'viewport'})
 assert h.page_ok(None,SimpleNamespace(result={'title':'Example','visible_text':['Visible'],'scope':'viewport'}))
 assert not h.page_ok(None,SimpleNamespace(result={'title':'Example','visible_text':['Invented'],'scope':'viewport'}))

def test_invalid_find_input_never_touches_device():
 for q in ['', 'x'*81, 'line\nbreak','🙂']:
  with pytest.raises(ValueError):h.find_text(object(),{'query':q},None)

def test_back_validator_rejects_unchanged_native_url(monkeypatch):
 result={'title':'Example','visible_text':['Visible'],'scope':'viewport','url':'https://example.org/','previous_url':'https://example.org/'}
 monkeypatch.setattr(h,'snapshot',lambda _:{'title':'Example','visible_text':['Visible'],'scope':'viewport'})
 assert not h.page_ok(None,SimpleNamespace(result=result))


def test_onboarding_cancels_only_verified_native_fennec_role_dialog():
 class D:
  cancelled=False
  native_reads=0
  def adb(self,*args):
   return 'mCurrentFocus=Window{x u0 '+(h.PKG+'/.App' if self.cancelled else 'com.google.android.permissioncontroller/com.android.permissioncontroller.role.ui.RequestRoleActivity')+'}'
  def dump_xml(self,*,use_portal=True):
   if self.cancelled:return '<hierarchy><node resource-id="ADDRESSBAR_URL_BOX" bounds="[0,0][100,100]"/></hierarchy>'
   if not use_portal:
    self.native_reads+=1
    return '<hierarchy><node text="Set Fennec as your default browser app?" bounds="[0,0][100,100]"/></hierarchy>'
   return '<hierarchy><node resource-id="ADDRESSBAR_URL_BOX" bounds="[0,0][100,100]"/></hierarchy>'
  def back(self):self.cancelled=True
 d=D();assert h.open_browser(d,{},None)['app']==h.PKG
 assert d.cancelled and d.native_reads==1


def test_unrecognised_native_role_dialog_is_not_dismissed_or_selected():
 class D:
  def adb(self,*args):return 'mCurrentFocus=Window{x u0 com.google.android.permissioncontroller/com.android.permissioncontroller.role.ui.RequestRoleActivity}'
  def dump_xml(self,*,use_portal=True):return '<hierarchy><node text="Unknown role request"/></hierarchy>'
  def back(self):pytest.fail('Must not interact with unknown role request')
 with pytest.raises(ValueError,match='Unknown OS role'):h.open_browser(D(),{},None)


@pytest.mark.parametrize('owner,allowed', [(h.PKG,True),('org.example.other',False)])
def test_native_popup_tap_requires_exact_focused_window_owner(owner,allowed):
 class D:
  taps=[]
  def adb(self,*args):return ('mCurrentFocus=Window{abc u0 PopupWindow:abcd}\n'
       '  Window #0 Window{abc u0 PopupWindow:abcd}:\n'
       '    mOwnerUid=12345\n    mAttrs={package='+owner+'}\n')
  def tap(self,*args):self.taps.append(args)
 d=D()
 if allowed:
  d.dump_xml=lambda **kwargs:'<hierarchy><node bounds="[0,0][20,20]"/></hierarchy>'
  h.tap(d,{'bounds':'[0,0][20,20]'});assert d.taps==[(10,10)]
 else:
  with pytest.raises(ValueError,match='focused window'):h.tap(d,{'bounds':'[0,0][20,20]'})
