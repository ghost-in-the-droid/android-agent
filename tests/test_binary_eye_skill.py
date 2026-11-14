import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
spec=importlib.util.spec_from_file_location('binary_eye_helpers',Path(__file__).parents[1]/'skillhub/ghost/binary-eye/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

def node(rid,text='',bounds='[0,0][100,100]',**extra):return {'resource-id':h.ID+rid,'text':text,'bounds':bounds,**extra}
def compose():
 return [node('content','Demo','[0,200][900,400]'),node('format','','[0,600][900,700]'),{'resource-id':'android:id/text1','text':'QR Code','bounds':'[0,610][800,690]'},node('unescape',checked='false'),node('encode')]

def test_invalid_content_never_touches_device():
 for text in ['', 'x'*513,'line\nbreak','🙂']:
  with pytest.raises(ValueError):h.set_content(object(),{'content':text},None)

def test_viewer_state_does_not_invent_decoded_content(monkeypatch):
 monkeypatch.setattr(h,'nodes',lambda _:[node('barcode',**{'content-desc':'View barcode'})])
 state=h.read_state(None,{},None)
 assert state['image_visible'] and 'content' not in state and 'format' not in state
 assert 'does not decode' in state['scope']

def test_generator_refuses_escape_expansion(monkeypatch):
 ns=compose();ns[3]['checked']='true';monkeypatch.setattr(h,'nodes',lambda _:ns)
 with pytest.raises(ValueError,match='Literal generator content'):h.generate(object(),{},None)

def test_qr_validator_rejects_wrong_content_and_wrong_format(monkeypatch):
 monkeypatch.setattr(h,'read_state',lambda *_:{'screen':'barcode'})
 result={'image_visible':True,'generated_content':'Demo','format':'QR Code'}
 ctx=SimpleNamespace(params={'content':'Demo'},result=result)
 assert h.generated_ok(None,ctx)
 result['format']='Aztec';assert not h.generated_ok(None,ctx)
 result['format']='QR Code';result['generated_content']='Different';assert not h.generated_ok(None,ctx)

def test_editor_validator_rereads_controls(monkeypatch):
 monkeypatch.setattr(h,'nodes',lambda _:compose());state=h.read_state(None,{},None)
 assert h.state_ok(None,SimpleNamespace(params={'content':'Demo','format':'QR Code'},result=state))
 assert not h.state_ok(None,SimpleNamespace(params={'format':'Aztec'},result=state))

def test_tap_refuses_foreign_focused_window():
 class Device:
  def adb(self,*_):return 'mCurrentFocus=Window{aa u0 com.android.systemui/.Shade}\nmFocusedApp=ActivityRecord{xx u0 '+h.PKG+'/.activity.EncodeActivity}'
  def tap(self,*_):pytest.fail('Foreign window must never receive a tap')
 with pytest.raises(ValueError,match='does not own'):h.tap(Device(),node('encode'))
