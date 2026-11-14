import importlib.util
from pathlib import Path
from types import SimpleNamespace
import html
import pytest

spec=importlib.util.spec_from_file_location('newpipe_helpers',Path(__file__).parents[1]/'skillhub/ghost/newpipe/helpers.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

def row(rid,text,top):
 return f'<node resource-id="{h.ID+rid}" text="{html.escape(text)}" bounds="[0,{top}][100,{top+40}]" />'
class Device:
 def __init__(self,xml):self.xml='<hierarchy>'+xml+'</hierarchy>';self.commands=[]
 def dump_xml(self):return self.xml
 def adb(self,*args):self.commands.append(args);return ''

def screen():
 return row('toolbar_search_edit_text','solar',80)+row('itemVideoTitleView','Solar panels',275)+row('itemUploaderView','Example channel',375)+row('itemAdditionalDetails','12K views • 1 year ago',421)+row('itemDurationView','04:59',415)

def test_incomplete_results_are_not_claimed():
 d=Device(screen()+row('itemVideoTitleView','Partial offscreen title',2180))
 assert h.read_results(d,{'limit':5},None)['count']==1

def test_validator_rejects_changed_query_or_metadata():
 d=Device(screen());payload=h.read_results(d,{'limit':1},None)
 assert h.results_ok(d,SimpleNamespace(params={'query':'solar'},result=payload))
 assert not h.results_ok(d,SimpleNamespace(params={'query':'wind'},result=payload))
 payload['videos'][0]['channel']='Wrong channel'
 assert not h.results_ok(d,SimpleNamespace(params={'query':'solar'},result=payload))

def test_preview_backing_results_are_not_returned():
 with pytest.raises(ValueError,match='preview|detail'):
  h.read_results(Device(screen()+row('detail_video_title_view','Preview',687)),{},None)

def test_invalid_search_never_touches_device():
 d=Device('')
 with pytest.raises(ValueError):h.search(d,{'query':'\n'},None)
 assert d.commands==[]


def test_cold_start_waits_without_backing_out_to_launcher(monkeypatch):
 d=Device('')
 def wait(_device, ready):
  assert not ready([])
  assert not ready([])
  assert ready([{'content-desc':'Open Drawer'}])
 monkeypatch.setattr(h,'wait',wait)
 assert h.open_app(d,{},None)['screen']=='home'
 assert d.commands==[('shell','am','start','-W','-S','-n',h.PKG+'/.MainActivity')]


def test_cold_wait_denies_notification_before_reading_app_tree(monkeypatch):
 d = Device('')
 calls = []
 def sweep(device, policy):
  assert device is d
  assert policy.get('allow_permissions') is None
  assert policy['deny_permissions'] == ['notifications']
  assert 'screen_recording' in policy['ignore']
  calls.append('sweep')
  return len(calls) == 1
 monkeypatch.setattr(h, 'sweep_if_system_dialog', sweep)
 monkeypatch.setattr(h, 'nodes', lambda device: [{'content-desc':'Open Drawer'}])
 assert h.wait(d, lambda ns: ns[0]['content-desc'] == 'Open Drawer')
 assert calls == ['sweep', 'sweep']


def test_tap_uses_settled_coordinates_instead_of_stale_scroll_position(monkeypatch):
 node = {'resource-id':'android:id/title', 'text':'Autoplay', 'bounds':'[45,2300][220,2361]'}
 moved = {**node, 'bounds':'[45,1950][220,2010]'}
 snapshots = iter([[node], [moved], [moved]])
 monkeypatch.setattr(h, 'nodes', lambda _: next(snapshots))
 monkeypatch.setattr(h.time, 'sleep', lambda _: None)
 taps = []
 d = SimpleNamespace(adb=lambda *args: 'mCurrentFocus=Window{x u0 org.schabi.newpipe/.SettingsActivity}',
                     tap=lambda x,y: taps.append((x,y)))
 h.tap(d, node)
 assert taps == [(132,1980)]


def test_tap_refuses_control_beyond_tested_display(monkeypatch):
 node = {'resource-id':'android:id/title', 'text':'Autoplay', 'bounds':'[45,2300][220,2361]'}
 monkeypatch.setattr(h, 'nodes', lambda _: [node])
 monkeypatch.setattr(h.time, 'sleep', lambda _: None)
 ticks = iter(range(10))
 monkeypatch.setattr(h.time, 'monotonic', lambda: next(ticks))
 d = SimpleNamespace(adb=lambda *args: pytest.fail('Off-screen control must cause no input'))
 with pytest.raises(ValueError,match='settle inside'):
  h.tap(d, node)






