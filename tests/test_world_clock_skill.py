"""Offline city selection and clock freshness, including midnight rollover."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
spec=importlib.util.spec_from_file_location('world_clock_helper',Path(__file__).parents[1]/'skillhub/ghost/world-clock/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

@pytest.mark.parametrize('value',['../../etc/passwd','Europe/Berlin;input keyevent HOME','NotARealArea/NoSuchCity','localhost'])
def test_zone_is_a_real_iana_identifier_before_input(value):
    with pytest.raises(ValueError):h.zone(value)

def test_named_public_zone_preserved():assert h.zone('Europe/Berlin')=='Europe/Berlin'

def test_system_clock_is_not_the_zham_foreground():
    class Device:
        def adb(self,*args):return 'mCurrentFocus=Window{abcd u0 com.sec.android.app.clockpackage/.ClockPackage}'
    with pytest.raises(ValueError,match='focused window'):h.foreground(Device())

@pytest.mark.parametrize('text',['25:00:00','00:60:00','00:00:60'])
def test_invalid_display_times_rejected(text):
    with pytest.raises(ValueError):h.seconds(text)

def test_live_clock_validator_accepts_midnight_tick_not_a_stale_hour(monkeypatch):
    monkeypatch.setattr(h,'nodes',lambda d:[]);monkeypatch.setattr(h,'clock_mode',lambda ns:True)
    monkeypatch.setattr(h,'rows',lambda ns:[{'zone':'Etc/UTC','city':'UTC','time':'00:00:01'}])
    class Device:
        def adb(self,*args):return '1'
    r={'screen':'clocks','clocks':[{'zone':'Etc/UTC','city':'UTC','time':'23:59:59'}]}
    assert h.clocks_ok(Device(),SimpleNamespace(result=r,params={}))
    r['clocks'][0]['time']='23:00:00'
    assert not h.clocks_ok(Device(),SimpleNamespace(result=r,params={}))
