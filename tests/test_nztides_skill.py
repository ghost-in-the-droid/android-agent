"""Native port identity, expiry and explicit-offset preservation contracts."""
import importlib.util,datetime
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('nz_helper',Path(__file__).parents[1]/'skillhub/ghost/nztides/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
NOW=datetime.datetime(2026,11,3,11,tzinfo=datetime.timezone.utc)
BODY='[Auckland]  1.9m ↑0.53m/hr\n---------------\nHigh tide (2.9m) in 3h00m\n\n 0.80 L 09:17 Tue 03/11/26 GMT+01:00\n 2.90 H 15:32 Tue 03/11/26 GMT+01:00\n 0.80 L 21:38 Tue 03/11/26 GMT+01:00\n'
def n(text='',desc='',cls='android.widget.TextView',box='[248,328][513,385]'):return {'text':text,'content-desc':desc,'class':cls,'bounds':box}
def table(body=BODY):return [n('NZ Tides'),n(desc='More options'),n(body,cls='android.widget.ScrollView',box='[0,180][959,2205]')]
def test_native_offset_and_preceding_tide_are_preserved():
    d=h.table(table(),NOW);assert d['events'][0]==dict(height_m='0.80',kind='low',time='09:17',date='2026-11-03',printed_date='03/11/26',time_zone='GMT+01:00');assert d['direction']=='rising'
def test_expired_table_is_rejected():
    with pytest.raises(ValueError):h.table(table(),NOW+datetime.timedelta(days=400))
def test_repeated_high_tide_is_rejected():
    with pytest.raises(ValueError):h.table(table(BODY.replace('2.90 H','2.90 L')),NOW)
def test_wrong_weekday_is_rejected():
    with pytest.raises(ValueError):h.table(table(BODY.replace('Tue','Mon')),NOW)
def test_offsetless_rows_are_rejected():
    with pytest.raises(ValueError):h.table(table(BODY.replace('GMT+01:00','')),NOW)
def test_unknown_port_header_is_rejected():
    with pytest.raises(ValueError):h.table(table(BODY.replace('[Auckland]','[Current location]')),NOW)
def test_picker_cannot_masquerade_as_tide_table():
    with pytest.raises(ValueError):h.table(table()+[n('Choose Port')],NOW)
@pytest.mark.parametrize('target',['Cancel','About','More options'])
def test_menu_and_cancel_labels_cannot_be_ports(target):
    with pytest.raises(ValueError,match='bundled port'):h.select_port(object(),{'port':target},None)
def test_nonvisible_known_port_requires_scrolling(monkeypatch):
    ns=[n('Choose Port'),n('Cancel'),n('Auckland')];monkeypatch.setattr(h,'nodes',lambda d:ns)
    with pytest.raises(ValueError,match='currently be exposed'):h.select_port(object(),{'port':'Gisborne'},None)
def test_cold_read_launches_only_from_proven_samsung_home(monkeypatch):
    class Device:
        def adb(self,*a):return 'mCurrentFocus=Window{abc u0 com.sec.android.app.launcher/.Launcher}'
    seen=[];monkeypatch.setattr(h,'open_app',lambda d,p,c:seen.append('open') or {'port':'Auckland'})
    assert h.read_tides(Device(),{},None)=={'port':'Auckland'} and seen==['open']
@pytest.mark.parametrize('focus',['com.android.vending/.Main','com.example.x/com.sec.android.app.launcher/Fake','PopupWindow:unknown'])
def test_cold_read_never_opens_from_foreign_or_unknown_focus(monkeypatch,focus):
    class Device:
        def adb(self,*a):return 'mCurrentFocus=Window{abc u0 '+focus+'}'
    def unexpected(*args):raise AssertionError('Foreign app must never be replaced by cold-read entry')
    monkeypatch.setattr(h,'open_app',unexpected)
    with pytest.raises(ValueError,match='focused window'):h.read_tides(Device(),{},None)
