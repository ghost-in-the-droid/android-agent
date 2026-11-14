"""Checked-year/weekday proof and public-table boundaries."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('holiday_helper',Path(__file__).parents[1]/'skillhub/ghost/deufeitage/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def n(text,box='[31,638][111,691]',cls='android.widget.TextView',**extra):return {'text':text,'bounds':box,'class':cls,**extra}
def table():
    ns=[n('Berlin',cls='android.widget.EditText'),n('',checked_year='2027'),n('Date'),n('Holiday'),n('Difference')]
    for i,(date,name) in enumerate([('Fri 01/01',"New Year's Day"),('Mon 03/08',"International Women's Day"),('Fri 03/26','Good Friday')]):
        y=730+i*126;ns+=[n(date,f'[31,{y}][223,{y+53}]'),n(name,f'[299,{y}][760,{y+53}]'),n('59 days',f'[914,{y}][1049,{y+53}]')]
    return ns
def test_checked_year_and_native_weekday_make_full_iso_dates():
    d=h.state(table());assert d['year']==2027 and d['holidays'][2]['date']=='2027-03-26'
def test_visible_unchecked_year_label_cannot_prove_selected_year():
    ns=table();ns[1]=n('2027')
    with pytest.raises(ValueError):h.state(ns)
def test_wrong_weekday_is_not_silently_accepted():
    ns=table();ns[5]['text']='Thu 01/01'
    with pytest.raises(ValueError):h.state(ns)
def test_incomplete_difference_cell_does_not_count_as_full_row():
    with pytest.raises(ValueError):h.state(table()[:-1])
def test_foreign_region_text_is_refused():
    ns=table();ns[0]['text']='Current location'
    with pytest.raises(ValueError):h.state(ns)
def test_other_rows_description_cannot_masquerade_as_first_holiday():
    with pytest.raises(ValueError):h.description(table()+[n('Unrelated public description '*5,'[31,1200][1049,1400]')],1)
@pytest.mark.parametrize('idx',[True,0,4,'1.0'])
def test_description_index_is_bounded_integer(idx):
    with pytest.raises(ValueError):h.index({'index':idx})
def test_year_must_be_currently_exposed_before_any_input(monkeypatch):
    monkeypatch.setattr(h,'nodes',lambda d:table())
    with pytest.raises(ValueError,match='currently be exposed'):h.select_year(object(),{'year':2035},None)
def test_native_checked_ancestor_is_used(monkeypatch):
    class Device:
        def dump_xml(self,**kw):return '<hierarchy><node package="'+h.PKG+'" checkable="true" checked="true" bounds="[599,460][743,601]"><node package="'+h.PKG+'" text="2027" bounds="[627,504][715,557]"/></node></hierarchy>'
    monkeypatch.setattr(h,'foreground',lambda d:None);assert h.nodes(Device())[0]['checked_year']=='2027'

def test_cli_numeric_index_string_is_accepted():
    assert h.index({'index':'1'})==1
