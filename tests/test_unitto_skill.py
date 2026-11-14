import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
import yaml
spec=importlib.util.spec_from_file_location('unitto_helpers',Path(__file__).parents[1]/'skillhub/ghost/unitto/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

def test_decimal_input_refuses_expressions_and_unbounded_values():
 for value in ['-1','1+2','1e6','NaN','1,000','1\n2','1234567890','0.1234567']:
  with pytest.raises(ValueError):h.value_param(value)
 assert h.value_param('26.2')=='26.2'

def test_displayed_grouping_is_read_without_changing_value():
 assert h.number('1\u00a0000.25')==h.Decimal('1000.25')
 for text in ['1,2','2+2','Infinity','']:
  with pytest.raises(ValueError):h.number(text)

def test_result_checker_accepts_rounding_but_rejects_wrong_units_and_values():
 s={'input_value':'26.2','output_value':'42.165','from_unit':'Mile','to_unit':'Kilometer'}
 assert h.result_matches(s)
 assert not h.result_matches({**s,'output_value':'42.164'})
 assert not h.result_matches({**s,'from_unit':'Foot'})

def test_entry_rejects_untested_app_version_before_launch():
 class D:
  def adb(self,*args):
   assert args==('shell','dumpsys','package',h.PKG)
   return 'versionCode=77 minSdk=26'
 with pytest.raises(ValueError,match='version code 76'):h.open_converter(D(),{},None)

def test_tap_never_reaches_foreign_foreground():
 class D:
  def adb(self,*_):return 'mCurrentFocus=Window{x u0 com.android.systemui/.Shade}'
  def tap(self,*_):pytest.fail('Must abort foreign tap')
 with pytest.raises(ValueError,match='focused window'):h.tap(D(),{'bounds':'[0,0][100,100]'})

def test_validator_rereads_and_checks_requested_units(monkeypatch):
 s={'input_value':'2.5','output_value':'250','from_unit':'Meter','to_unit':'Centimeter'}
 monkeypatch.setattr(h,'read_state',lambda *_:dict(s))
 assert h.state_ok(None,SimpleNamespace(result=dict(s),params={'value':'2.5','from_unit':'Meter','to_unit':'Centimeter'}))
 assert not h.state_ok(None,SimpleNamespace(result=dict(s),params={'to_unit':'Mile'}))

def test_composite_feet_editor_is_explicitly_unsupported():
 with pytest.raises(ValueError,match="Unsupported length unit"):
  h.set_units(object(),{"from_unit":"Foot","to_unit":"Meter"},None)

def test_nodes_use_native_dump_and_exclude_foreign_shadow_controls():
 class D:
  def adb(self,*_):return 'mCurrentFocus=Window{x u0 '+h.PKG+'/.MainActivity}'
  def dump_xml(self,*,use_portal):
   assert use_portal is False
   return '<hierarchy><node package="'+h.PKG+'" text="Mile" enabled="true" bounds="[0,1][20,30]"/><node package="other.app" text="Mile" enabled="true" bounds="[0,40][20,70]"/></hierarchy>'
 assert [n['package'] for n in h.nodes(D())]==[h.PKG]

def test_unit_selection_waits_past_old_converter_label(monkeypatch):
 def n(text,cls,bounds,desc=''):
  return {'text':text,'class':cls,'bounds':bounds,'content-desc':desc}
 swap=n('','android.view.View','[500,500][550,550]','Swap units')
 old=[swap,n('Kilometer','android.widget.TextView','[50,500][400,550]')]
 new=[swap,n('Mile','android.widget.TextView','[50,500][400,550]')]
 picker=[n('','android.view.View','[0,0][50,50]','Navigate up'),n('','android.widget.EditText','[100,0][800,100]'),n('Mile','android.widget.TextView','[50,200][900,250]')]
 states=iter([old,picker,picker,old,new]);seen=[]
 def next_nodes(_):
  state=next(states);seen.append(state);return state
 monkeypatch.setattr(h,'nodes',next_nodes)
 monkeypatch.setattr(h,'tap',lambda *_:None)
 monkeypatch.setattr(h.time,'sleep',lambda _:None)
 class D:
  def adb(self,*_):return 'mCurrentFocus=Window{x u0 '+h.PKG+'/.MainActivity}'
 h.choose_unit(D(),'Mile','from_unit')
 assert seen[-1] is new and len(seen)==5

def test_discovery_exposes_exact_supported_unit_choices():
 path=Path(__file__).parents[1]/'skillhub/ghost/unitto/skill.yaml'
 manifest=yaml.safe_load(path.read_text())
 for action in manifest['actions']:
  if action['name'] not in {'set_units','convert_length'}:continue
  choices={p['name']:p for p in action['params']}
  for name in ['from_unit','to_unit']:
   assert choices[name]['type']=='enum'
   assert set(choices[name]['values'])==set(h.FACTORS)
