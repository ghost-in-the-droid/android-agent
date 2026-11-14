"""RSS URL boundaries, native ownership and preview selection regressions."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('feeder_helper',Path(__file__).parents[1]/'skillhub/ghost/feeder/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

@pytest.mark.parametrize('url',['http://example.org/rss.xml','https://127.0.0.1/rss','https://user:secret@example.org/rss','https://example.org/rss?token=secret','https://example.local/rss','https://example.org/rss#private','https://example.org:443/rss'])
def test_nonpublic_or_credential_bearing_url_refused(url):
    with pytest.raises(ValueError,match='public HTTPS'):h.public_url(url)

def test_public_feed_url_preserved_exactly():
    url='https://feeds.bbci.co.uk/news/science_and_environment/rss.xml'
    assert h.public_url(url)==url

class Device:
    def __init__(self,focus='other.app/.Main'):self.focus=focus;self.inputs=[]
    def adb(self,*args):return 'mCurrentFocus=Window{abcd u0 '+self.focus+'}'
    def dump_xml(self,**kwargs):return '<hierarchy/>'
    def tap(self,*args):self.inputs.append(args)

def test_foreign_focus_refuses_a_stale_preview():
    d=Device()
    with pytest.raises(ValueError,match='focused window'):h.tap(d,{'bounds':'[137,896][1013,1032]'},long=True)
    assert not d.inputs

def test_feed_toolbar_and_partial_card_are_not_article_choices():
    assert not h.previews([{'class':'android.widget.TextView','text':'A long enough toolbar title that should not be a preview','bounds':'[137,100][1013,209]'},{'class':'android.widget.TextView','text':'A partial headline and excerpt at the bottom of the display','bounds':'[137,2200][1013,2340]'}])

def test_back_refuses_unknown_screen_before_input():
    d=Device(h.PKG+'/.Main')
    with pytest.raises(ValueError,match='restricted'):h.back_to_list(d,{},None)
    assert not d.inputs

def test_native_reader_requires_internal_reader_controls():
    assert not h.article([{'content-desc':'Go back'},{'content-desc':'Open in default browser'}])
