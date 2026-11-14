import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
spec=importlib.util.spec_from_file_location('checkers_helpers',Path(__file__).parents[1]/'skillhub/ghost/checkers/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def node(text='',id='',bounds=(0,0,100,100)):return dict(text=text,id=id,bounds=bounds)
def test_repeated_new_game_confirms_only_the_known_overwrite_dialog(monkeypatch):
 state={'screen':'menu'};taps=[]
 class Device:
  def tap(self,x,y,**_):
   taps.append((x,y));state['screen']='overwrite' if state['screen']=='menu' else 'board'
 def nodes(_):
  if state['screen']=='menu':return [node('bot',h._ID+'section_label'),node('NEW GAME',h._ID+'play_button')]
  if state['screen']=='overwrite':return [node('Overwrite resumable game?',h._ID+'alertTitle'),node('YES','android:id/button1',bounds=(100,100,200,200))]
  return []
 monkeypatch.setattr(h,'_nodes',nodes);monkeypatch.setattr(h,'read_turn',lambda _:dict(in_game=state['screen']=='board',text="White player's turn"))
 result=h.start(Device(),{'opponent':'bot'},None)
 assert result['data']['turn']['in_game'] and taps==[(50,50),(150,150)]
def test_unknown_positive_dialog_is_never_confirmed(monkeypatch):
 monkeypatch.setattr(h,'_nodes',lambda _:[node('Different question',h._ID+'alertTitle'),node('YES','android:id/button1')])
 class Device:
  def tap(self,*_,**kw):pytest.fail('Unknown confirmation must not be tapped')
 assert not h._confirm_overwrite(Device())
@pytest.mark.parametrize('log,moves,expected',[
 ([{'accepted':False}],'c3-b4',False),([{'accepted':True}],'c3-b4,e3-d4',False),
 ([{'accepted':True},{'accepted':False}],'c3-b4,e3-d4',False),
 ([{'accepted':True},{'accepted':True}],'c3-b4,e3-d4',True),([], '',False)])
def test_multi_move_validator_requires_every_requested_move_accepted(monkeypatch,log,moves,expected):
 monkeypatch.setattr(h,'read_turn',lambda _:dict(in_game=True,game_over=False))
 assert h.moves_played(None,SimpleNamespace(result={'log':log},params={'moves':moves})) is expected

def test_multi_move_refuses_dialog_or_menu_before_any_tap(monkeypatch):
 monkeypatch.setattr(h,'read_turn',lambda _:dict(in_game=False))
 class Device:
  def tap(self,*_,**kw):pytest.fail('No taps outside a game')
 with pytest.raises(RuntimeError,match='no running game'):h.play_moves(Device(),{'moves':'c3-b4'},None)
