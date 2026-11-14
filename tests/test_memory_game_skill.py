import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
spec=importlib.util.spec_from_file_location('memory_game_helpers',Path(__file__).parents[1]/'skillhub/ghost/memory-game/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def node(text='',id='',bounds=(0,0,100,100)):return dict(text=text,id=id,bounds=bounds)
def test_restart_confirms_quit_after_back_but_resume_cancels(monkeypatch):
 state={'screen':'game'};taps=[]
 def nodes(_):
  if state['screen']=='game':return [node(id=h._ID+'timerView')]
  if state['screen']=='menu':return [node(id=h._ID+'playButton')]
  return [node('Do you want to quit the game?','android:id/message'),node('YES','android:id/button1',(100,100,200,200)),node('NO','android:id/button2')]
 class Device:
  def back(self):state['screen']='dialog'
  def tap(self,x,y,**_):taps.append((x,y));state['screen']='menu' if x==150 else 'game'
 monkeypatch.setattr(h,'_nodes',nodes);monkeypatch.setattr(h.time,'sleep',lambda _:None)
 h.leave_game(Device(),{},None);assert state['screen']=='menu' and taps==[(150,150)]
 state['screen']='dialog';h.resume_game(Device(),{},None);assert state['screen']=='game' and taps[-1]==(50,50)
def test_unrelated_dialog_cannot_be_confirmed_or_cancelled(monkeypatch):
 monkeypatch.setattr(h,'_nodes',lambda _:[node('An unknown question','android:id/message'),node('YES','android:id/button1'),node('NO','android:id/button2')])
 class Device:
  def tap(self,*_,**kw):pytest.fail('Unknown dialog must not be answered')
 assert not h._answer_quit(Device(),leave=True)
 assert not h._answer_quit(Device(),leave=False)
def test_known_dialog_with_missing_answer_fails_closed(monkeypatch):
 monkeypatch.setattr(h,'_nodes',lambda _:[node('Do you want to quit the game?','android:id/message')])
 with pytest.raises(RuntimeError,match='missing'):h._answer_quit(object(),leave=True)
@pytest.mark.parametrize('tries,found,expected',[(1,0,True),(1,1,True),(0,0,False)])
def test_pair_validator_requires_observed_attempt_counter_increase(monkeypatch,tries,found,expected):
 monkeypatch.setattr(h,'read_status',lambda _:dict(in_game=True,tries=tries,pairs_found=found))
 assert h.pair_tried(None,SimpleNamespace(result={'before':{'tries':0}})) is expected
