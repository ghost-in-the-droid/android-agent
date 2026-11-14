"""Browse-only boundaries and active-player refusal."""
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
spec=importlib.util.spec_from_file_location('xtra_helper',Path(__file__).parents[1]/'skillhub/ghost/xtra/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

def test_empty_player_container_is_only_a_stub():
    assert not h.playback_tree(ET.fromstring('<hierarchy><node resource-id="'+h.ID+'playerContainer"/></hierarchy>'))

@pytest.mark.parametrize('child',['<node class="android.view.SurfaceView"/>','<node class="android.view.TextureView"/>','<node resource-id="'+h.ID+'exo_content_frame"/>','<node content-desc="Pause"/>','<node resource-id="'+h.ID+'playerContainer"><node/></node>'])
def test_playback_surface_or_player_content_is_detected(child):
    assert h.playback_tree(ET.fromstring('<hierarchy>'+child+'</hierarchy>'))

class Device:
    def __init__(self):self.commands=[];self.inputs=[]
    def adb(self,*args):
        self.commands.append(args)
        return 'mCurrentFocus=Window{abcd u0 '+h.PKG+'/.Main}'
    def dump_xml(self,**kwargs):return '<hierarchy><node class="android.view.SurfaceView"/></hierarchy>'
    def tap(self,*args):self.inputs.append(args)

def test_detected_player_is_stopped_before_any_input():
    d=Device()
    with pytest.raises(ValueError,match='Xtra stopped'):h.nodes(d)
    assert ('shell','am','force-stop',h.PKG) in d.commands and not d.inputs

def test_stream_card_cannot_be_selected_as_a_game(monkeypatch):
    d=Device();monkeypatch.setattr(h,'nodes',lambda d:[{'resource-id':h.ID+'username','text':'public_streamer','bounds':'[220,1109][500,1162]'}])
    with pytest.raises(ValueError,match='game-category'):h.open_game(d,{'index':0},None)
    assert not d.inputs

def test_game_counts_stay_literal_ui_labels():
    def n(rid,text,y):return {'resource-id':h.ID+rid,'text':text,'bounds':f'[217,{y}][800,{y+50}]'}
    rows=h.game_rows([n('gameName','Demo category',400),n('viewers','151.2K viewers',460),n('broadcastersCount','722 broadcasters',520)])
    assert rows[0][1]=={'index':0,'name':'Demo category','viewers':'151.2K viewers','broadcasters':'722 broadcasters'}
