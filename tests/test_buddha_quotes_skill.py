"""Read-only quote screen boundaries."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('buddha_helper',Path(__file__).parents[1]/'skillhub/ghost/buddha-quotes/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def n(id,text=''):return {'resource-id':h.PKG+':id/'+id,'text':text,'bounds':'[42,659][1041,1045]'}
def test_quote_requires_next_and_like_on_same_screen():
    ns=[n('quote','An offline thought about attention.'),n('next'),n('like')];assert h.state(ns)['quote'].startswith('An offline')
    with pytest.raises(ValueError):h.state(ns[:-1])
def test_drawer_overlay_cannot_be_read_as_quote():
    with pytest.raises(ValueError):h.state([n('quote','An offline thought about attention.'),n('next'),n('like'),{'content-desc':'Close navigation drawer'}])
def test_foreign_app_receives_no_next_tap():
    class Device:
        def adb(self,*a):return 'mCurrentFocus=Window{abcd u0 foreign.app/.Main}'
        def tap(self,*a):raise AssertionError('No input')
    with pytest.raises(ValueError):h.next_quote(Device(),{},None)
