"""Public catalog rows, title queries, and metadata-only navigation boundaries."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('myne_helper',Path(__file__).parents[1]/'skillhub/ghost/myne/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
@pytest.mark.parametrize('q',['x','Pride\nand Prejudice','a; input keyevent HOME','$(hostname)','https://example.org','a'*71])
def test_title_query_rejects_commands_urls_and_unbounded_input(q):
    with pytest.raises(ValueError):h.term(q)
def n(text='',desc='',box='[0,0][1080,150]',cls='android.widget.TextView'):return {'text':text,'content-desc':desc,'bounds':box,'class':cls}
def rows():return [n(desc='Home'),n('Pride and Prejudice',box='[56,80][1024,244]',cls='android.widget.EditText')]+sum(([n(desc='Book cover image',box=f'[62,{y}][394,{y+450}]'),n('Pride and Prejudice',box=f'[456,{y+40}][984,{y+110}]'),n('Jane Austen',box=f'[456,{y+116}][984,{y+181}]'),n('English',box=f'[456,{y+215}][619,{y+288}]')] for y in [328,856]),[])
def test_two_native_cover_rows_are_not_merged():assert len(h.results(rows())['books'])==2

def test_card_cannot_borrow_language_from_next_card():
    ns=rows();del ns[5]
    with pytest.raises(ValueError):h.results(ns)
def test_default_catalog_rows_cannot_certify_unfinished_title_search():
    ns=rows();ns[3]['text']='Moby Dick'
    with pytest.raises(ValueError):h.results(ns)
def test_reader_or_download_screen_cannot_supply_metadata():
    with pytest.raises(ValueError):h.book([n('Pride and Prejudice'),n('Reading')])
def test_foreign_app_receives_no_catalog_tap():
    class Device:
        def adb(self,*a):return 'mCurrentFocus=Window{abcd u0 foreign.app/.Main}'
        def tap(self,*a):raise AssertionError('No input')
    with pytest.raises(ValueError):h.tap(Device(),n('Download'))

def test_catalog_rejects_onboarding_even_with_complete_background_rows():
    ns=rows()+[n('Get Started'),n('Thanks for installing Myne!')]
    with pytest.raises(ValueError,match='post-onboarding'):h.catalog_data(ns)
