"""Public astronomy text and wallpaper/export-control boundaries."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('apod_helper',Path(__file__).parents[1]/'skillhub/ghost/apodroid/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def n(text='',desc='',cls='android.widget.TextView',box='[45,1476][900,1634]',click='false'):return {'text':text,'content-desc':desc,'class':cls,'bounds':box,'clickable':click}
def picture():return [n(desc='Astronomy picture',cls='android.widget.ImageView',box='[0,80][1080,1431]'),n('Astronomy picture'),n('3 November 2026',box='[45,1634][364,1691]'),n(desc='Show explanation')]
def test_native_title_and_date_must_correspond_to_image():
    ns=picture();assert h.picture(ns)['date']=='2026-11-03';ns[1]['text']='Different picture'
    with pytest.raises(ValueError):h.picture(ns)
def test_video_day_is_explicitly_a_static_frame():
    ns=picture();ns[2]['text']+=' · Video';assert h.picture(ns)['media_type']=='static_video_day_frame'
def test_unexpanded_settings_text_cannot_masquerade_as_explanation():
    with pytest.raises(ValueError):h.explanation(picture()+[n('Background settings text '*10,box='[0,1736][1080,2205]',click='true')])
@pytest.mark.parametrize('control',['Save','Set as wallpaper',"Choose the wallpaper's part",'Saved'])
def test_only_explanation_controls_can_be_tapped(control):
    with pytest.raises(ValueError,match='Only explanation'):h.tap_control(object(),[],control)
def test_missing_wallpaper_guard_fails_closed():
    class Device:
        def adb(self,*a):return 'WRITE_WALLPAPER: allow'
    with pytest.raises(ValueError):h.protected(Device())
