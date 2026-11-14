"""Offline catalog extraction, partial-row and foreign-focus regressions."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]/'skillhub/ghost/birdipedia'
spec=importlib.util.spec_from_file_location('birdipedia_helpers',ROOT/'helpers.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)


def n(text='',cls='android.widget.TextView',x=388,y=500,height=68,desc=''):
    return {'text':text,'desc':desc,'id':'','cls':cls,'package':h.PKG,'bounds':(x,y,1080,y+height),'checked':False}


def catalog(query='robin'):
    return [n(query,cls='android.widget.EditText',x=157,y=57,height=180),n(desc='Menu'),
            n('Filter by Name',x=202,y=60),n('Passeriformes',x=28,y=265),
            n('Lesser Ground Robin',y=485),n('Amalocichla incerta',y=576),
            n('Greater Ground Robin',y=868),n('Amalocichla sclateriana',y=959),
            n('Clipped Robin',y=1251,height=10),n('Clippus partialis',y=1290)]


def test_native_pairs_use_names_not_weekday_or_group_labels():
    assert h.state(catalog()) == {'query':'robin','birds':[
        {'common_name':'Lesser Ground Robin','scientific_name':'Amalocichla incerta'},
        {'common_name':'Greater Ground Robin','scientific_name':'Amalocichla sclateriana'}],
        'taxonomic_groups':['Passeriformes']}


def test_partial_name_does_not_count_as_complete_result():
    rows=catalog();rows[7]['bounds']=(388,868,1080,878)
    with pytest.raises(ValueError,match='Two complete'):h.state(rows)


def test_query_mismatch_refuses_stale_results():
    with pytest.raises(ValueError,match='match the exposed query'):h.state(catalog('eagle'))


def test_ambiguous_pair_does_not_guess():
    rows=catalog();rows.append(n('Second possible common name',y=485))
    with pytest.raises(ValueError,match='Two complete'):h.state(rows)


@pytest.mark.parametrize('query',[None,'','a; reboot','bird\nname','鸟','a'*41,False])
def test_invalid_query_never_drives_device(query):
    with pytest.raises(ValueError,match='ASCII'):h.filter_birds(None,{'query':query},None)


def test_foreign_foreground_refuses_entry_and_read():
    class D:
        def foreground_package(self):return 'com.example.unrelated'
        def adb(self,*args):pytest.fail('must not launch')
        def dump_xml(self,**kwargs):pytest.fail('must not read')
    with pytest.raises(ValueError,match='unrelated'):h.open_app(D(),{},None)
    with pytest.raises(ValueError,match='foreground'):h.read_results(D(),{},None)


def test_empty_results_fail_without_inventing_catalog_rows():
    with pytest.raises(ValueError,match='Two complete'):h.state(catalog()[:4])


@pytest.mark.parametrize("status,backs", [("mInputShown=true",1),("mInputShown=false",0),
                                        ("mIsInputViewShown=true",1),("",0)])
def test_keyboard_back_requires_proven_ime_and_keeps_app_focus(status,backs):
    calls=[]
    class D:
        def foreground_package(self):return h.PKG
        def adb(self,*args):return status
        def back(self,**kwargs):calls.append('BACK')
    h.hide_keyboard(D())
    assert len(calls)==backs
