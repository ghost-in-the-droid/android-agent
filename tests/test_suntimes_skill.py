"""Named-city, denied-location and native table proof boundaries."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('sun_helper',Path(__file__).parents[1]/'skillhub/ghost/suntimes/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def n(text='',rid='',box='[56,717][936,770]'):
    return {'text':text,'resource-id':rid if ':' in rid else h.PKG+':id/'+rid,'class':'android.widget.TextView','bounds':box}
def table():
    return [n(rid='action_location_add'),n('Berlin',box='[202,91][346,167]')]+[n(v,k) for k,v in {'text_date':'Today\nNov 3, 2026 [w]','text_timezone':'Europe/Berlin [d][w]','text_time_sunrise_actual':'7:04 AM','text_time_sunset_actual':'4:34 PM','text_daylength':'9h 29m in the day','text_info_moonphase':'Waning Crescent'}.items()]
def test_table_omits_missing_moon_events_without_inventing_times():
    result=h.state(table());assert result['date']=='2026-11-03' and result['moonrise'] is None and result['moonset'] is None
@pytest.mark.parametrize('city',['Current (last known)','Phoenix','52.5,13.4'])
def test_only_known_bundled_city_headers_are_read(city):
    ns=table();ns[1]['text']=city
    with pytest.raises(ValueError):h.state(ns)
def test_wrong_time_zone_is_rejected():
    ns=table();next(n for n in ns if n['resource-id'].endswith('/text_timezone'))['text']='America/Phoenix'
    with pytest.raises(ValueError):h.state(ns)
def test_civil_twilight_cannot_replace_missing_actual_sunrise():
    ns=[n for n in table() if not n['resource-id'].endswith('/text_time_sunrise_actual')]+[n('6:28 AM','text_time_sunrise_civil')]
    with pytest.raises(ValueError):h.state(ns)
def test_search_requires_exact_query_and_matching_city_row():
    with pytest.raises(ValueError):h.searched([n('Hamburg','search_src_text'),n('Hamburg-West','android:id/text1')],'Hamburg')
def test_location_guard_refuses_allowed_gps():
    class Device:
        def adb(self,*a):return 'FINE_LOCATION: allow'
    with pytest.raises(ValueError):h.protected(Device())
def test_popup_ownership_does_not_accept_an_unrelated_window_block():
    class Device:
        def adb(self,*a):return 'mCurrentFocus=Window{abc u0 PopupWindow:x}\n  Window #1 Window{def u0 PopupWindow:x}\n package='+h.PKG+' mOwnerUid=12345\n'
    with pytest.raises(ValueError):h.foreground(Device())
def test_dialog_cannot_masquerade_as_table():
    with pytest.raises(ValueError):h.state(table()+[n('Location','dialog_title')])
