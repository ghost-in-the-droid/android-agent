"""Public abstract and metadata pairing, with no PDF/download operations."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('arxiv_helper',Path(__file__).parents[1]/'skillhub/ghost/arxiv/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
@pytest.mark.parametrize('value',['x','a; input keyevent HOME','$(hostname)','https://example.org','a'*81])
def test_query_is_bounded_public_plain_text(value):
    with pytest.raises(ValueError):h.term(value)
def n(rid,text,y):return {'resource-id':h.PKG+':id/'+rid,'text':text,'bounds':f'[77,{y}][1003,{y+50}]','class':'android.widget.TextView'}
def card(y=300):return [n('paper_title','Quantum channel tomography',y),n('paper_authors','Public Authors',y+100),n('paper_published_date','Submitted: 11/2/26',y+200),n('paper_id','ID: 2611.03639v1',y+250),n('paper_categories','quant-ph',y+300),n('paper_summary','An exposed public abstract that describes a research result. '*5,y+400)]
def test_exposed_abstract_is_returned_without_downloading():
    result=h.paper(card());assert result['arxiv_id']=='ID: 2611.03639v1' and 'not full paper/PDF' in result['scope']
def test_card_cannot_borrow_abstract_from_next_paper():
    ns=card()[:-1]+card(1200)
    with pytest.raises(ValueError):h.paper(ns)
def test_foreign_focus_blocks_all_taps():
    class Device:
        def adb(self,*args):return 'mCurrentFocus=Window{abcd u0 foreign.app/.Main}'
        def tap(self,*args):raise AssertionError('No input allowed')
    with pytest.raises(ValueError):h.tap(Device(),n('menu_search','Search',100))
def test_downloaded_library_cannot_open_search(monkeypatch):
    monkeypatch.setattr(h,'nodes',lambda d:[n('paper_title','Private downloaded paper',300)])
    with pytest.raises(ValueError,match='Public dashboard'):h.prepare_search(object(),{},None)
