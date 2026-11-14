"""Catalog query, nested-tag and recipe-provenance boundaries."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('bc_helper',Path(__file__).parents[1]/'skillhub/ghost/based-cooking/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def n(desc='',text='',box='[0,158][1080,397]',cls='android.view.View'):return {'content-desc':desc,'text':text,'bounds':box,'class':cls}
def catalog():
    return [n(text='apple',box='[45,11][1035,146]',cls='android.widget.EditText'),n('Apple Chicken'),n(' apple',box='[653,250][813,385]'),n(' chicken',box='[264,250][458,385]'),n('Apple strudel',box='[0,397][1080,636]'),n(' dessert',box='[45,489][236,624]')]
def recipe():return [n(text='Apple Chicken',box='[68,90][1013,169]'),n(text='🗓 2022-07-11 🧑‍🍳 public-author',box='[68,191][1013,236]'),n(text='Ingredients',box='[68,1019][1013,1083]')]
def test_query_and_tags_are_native_metadata():
    d=h.results(catalog());assert d['query']=='apple' and d['recipes'][0]['tags']==['chicken','apple']
def test_partial_card_cannot_be_a_second_complete_result():
    ns=catalog();ns[4]['bounds']='[0,397][1080,500]'
    with pytest.raises(ValueError):h.results(ns)
def test_result_titles_must_match_native_query():
    ns=catalog();ns[4]['content-desc']='Banana pudding'
    with pytest.raises(ValueError):h.results(ns)
def test_recipe_returns_provenance_without_claiming_full_recipe_text():
    d=h.metadata(recipe());assert d['title']=='Apple Chicken' and 'Ingredients' not in str(d)
def test_about_screen_cannot_masquerade_as_recipe():
    with pytest.raises(ValueError):h.metadata([n(text='About Based Cooking')])
def test_header_tap_stays_above_nested_tag_chips(monkeypatch):
    seen=[]
    class Device:
        def tap(self,x,y):seen.append((x,y))
    monkeypatch.setattr(h,'nodes',lambda d:catalog());monkeypatch.setattr(h,'foreground',lambda d:None);monkeypatch.setattr(h,'wait',lambda d,pred:recipe())
    assert h.open_recipe(Device(),{'index':'1'},None)['title']=='Apple Chicken';assert seen==[(540,198)] and seen[0][1]<250
def menu():return [n('Search',box='[667,1887][833,1960]'),n('About',box='[681,1730][833,1803]'),n(box='[878,1859][1035,1988]',cls='android.widget.Button'),n(box='[878,1702][1035,1831]',cls='android.widget.Button')]
def test_search_uses_label_paired_button_not_about():assert h.bounds(h.search_button(menu()))[1]==1859
def test_ambiguous_search_geometry_is_refused():
    with pytest.raises(ValueError):h.search_button(menu()+[n(box='[878,1859][1035,1988]',cls='android.widget.Button')])
def test_shell_metacharacters_are_rejected_before_any_action():
    with pytest.raises(ValueError):h.search_recipes(object(),{'query':'apple; echo x'},None)
def test_foreign_focus_is_never_replaced_by_entry():
    calls=[]
    class Device:
        def adb(self,*a):calls.append(a);return 'mCurrentFocus=Window{abc u0 com.android.vending/.Main}'
    with pytest.raises(ValueError):h.open_app(Device(),{},None)
    assert not any('am' in a for a in calls)
