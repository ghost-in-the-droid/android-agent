"""Public catalog pairing, native detail proof and reminder refusal."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('gg_helper',Path(__file__).parents[1]/'skillhub/ghost/giggity/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def n(text='',desc='',rid='',box='[84,344][949,427]',cls='android.widget.TextView',**extra):return {'text':text,'content-desc':desc,'resource-id':h.PKG+':id/'+rid if rid else '', 'bounds':box,'class':cls,**extra}
def catalog():
    ns=[n('Giggity'),n(desc='Settings'),n(desc='Add...')]
    for i,title in enumerate(['Public event A','Public event B','Public event C']):
        y=344+i*150;ns+=[n(title,rid='title',box=f'[84,{y}][949,{y+83}]'),n('14–15 November 2026',rid='subtitle',box=f'[84,{y+83}][949,{y+140}]')]
    return ns
def program():return [n(desc='Show drawer'),n(desc='Search'),n('Sat 14 November, Public event',box='[158,121][944,197]'),n('18:30',box='[180,238][315,286]'),n('Room',box='[0,286][180,421]'),n('Code Sprint',box='[384,558][1080,688]')]
def detail(checked='false',body='Public session description'):
    return [n('Code Sprint',rid='title'),n('Room',rid='room'),n('Sat 14 November 19:00–03:00',rid='time'),n(body,rid='description'),n('Remind me',cls='android.widget.CheckBox',checked=checked)]
def test_catalog_pairs_only_adjacent_complete_native_date_rows():
    assert len(h.catalog(catalog())['conferences'])==3
    with pytest.raises(ValueError):h.catalog(catalog()[:-1])
def test_program_returns_labels_without_inventing_grid_durations_or_rooms():
    data=h.program(program());assert data['exposed_session_titles']==['Code Sprint'] and 'duration' not in data and 'rooms' not in data
@pytest.mark.parametrize('checked',['true','',None])
def test_session_read_requires_explicitly_unchecked_reminder(checked):
    with pytest.raises(ValueError):h.details(detail(checked))
def test_reminder_checkbox_can_never_be_tapped():
    with pytest.raises(ValueError,match='forbidden reminder'):h.tap(object(),n('Remind me',cls='android.widget.CheckBox'))
def test_description_preview_is_explicitly_truncated():
    d=h.details(detail(body='x'*450));assert len(d['description_preview'])==400 and d['description_truncated'] is True
def test_duplicate_native_session_name_is_refused_before_input(monkeypatch):
    monkeypatch.setattr(h,'nodes',lambda d:program()+[n('Code Sprint',box='[400,800][1000,930]')])
    with pytest.raises(ValueError,match='unique exposed'):h.open_session(object(),{'title':'Code Sprint'},None)
def test_overlapping_native_session_point_is_refused(monkeypatch):
    monkeypatch.setattr(h,'nodes',lambda d:program()+[n('Overlay session',box='[390,550][900,650]')])
    with pytest.raises(ValueError,match='Overlapping'):h.open_session(object(),{'title':'Code Sprint'},None)
def test_unexposed_conference_name_is_refused(monkeypatch):
    monkeypatch.setattr(h,'nodes',lambda d:catalog())
    with pytest.raises(ValueError,match='unique exposed'):h.open_conference(object(),{'name':'Private custom schedule'},None)
def test_foreign_focus_never_triggers_cold_catalog_entry(monkeypatch):
    class Device:
        def adb(self,*a):return 'mCurrentFocus=Window{abc u0 com.android.vending/.Main}'
    monkeypatch.setattr(h,'open_app',lambda *a:pytest.fail('must not launch'))
    with pytest.raises(ValueError):h.read_catalog(Device(),{},None)
