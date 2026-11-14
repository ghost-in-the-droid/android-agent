"""Native definition pairing and query-only clearing boundaries."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('dictionary_helper',Path(__file__).parents[1]/'skillhub/ghost/dictionary/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

@pytest.mark.parametrize('word',['x','word;input keyevent HOME','user@example.org','two words','$(hostname)','éclair'])
def test_query_is_one_bounded_ascii_word(word):
    with pytest.raises(ValueError):h.term(word)

def test_word_case_normalized():assert h.term('Serendipity')=='serendipity'

def n(text,box,cls='android.widget.TextView',desc=''):
    return {'text':text,'bounds':box,'class':cls,'content-desc':desc}

def test_definition_pairs_with_its_row_not_other_text():
    ns=[n('Definition','[68,949][276,1017]'),n('A fortunate unexpected discovery.','[341,767][1008,1107]'),n('Unrelated settings text','[341,1600][1008,1700]')]
    assert h.values(ns,'Definition')==['A fortunate unexpected discovery.']

def test_edited_unsubmitted_query_does_not_relabel_old_entry():
    ns=[n('entropy','[56,2019][1024,2177]','android.widget.EditText'),n('serendipity','[71,342][305,410]'),n('Type','[122,653][223,721]'),n('Noun','[341,608][455,676]'),n('Definition','[68,949][276,1017]'),n('A fortunate unexpected discovery.','[341,767][1008,1107]')]
    assert h.entry(ns) is None

def test_clear_refuses_a_history_screen_with_an_editable_field(monkeypatch):
    ns=[n('saved term','[56,2019][1024,2177]','android.widget.EditText'),n('Search History','[45,141][400,198]'),n('','[90,2065][158,2133]',desc='Clear')]
    monkeypatch.setattr(h,'nodes',lambda d:ns)
    class Device:
        def tap(self,*args):raise AssertionError('No input is allowed on history screen')
    with pytest.raises(ValueError,match='Main dictionary search'):h.clear_query(Device(),{},None)

def test_foreign_app_cannot_receive_dictionary_input():
    class Device:
        def adb(self,*args):return 'mCurrentFocus=Window{abcd u0 other.app/.Main}'
        def tap(self,*args):raise AssertionError('Unexpected tap')
    with pytest.raises(ValueError,match='focused window'):h.tap(Device(),n('Search','[0,300][200,400]'))
