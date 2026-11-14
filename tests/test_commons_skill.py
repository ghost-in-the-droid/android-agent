"""Anonymous feed selection and caption/credit boundaries; no image opening."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('commons_helper',Path(__file__).parents[1]/'skillhub/ghost/commons/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def n(rid='',text='',desc='',box='[0,0][1080,150]',selected='false'):return {'resource-id':h.PKG+':id/'+rid if rid else '', 'text':text,'content-desc':desc,'bounds':box,'selected':selected}
def feed():return [n(desc='Explore',selected='true'),n(desc='FEATURED',selected='true'),n('action_search'),n('categoryImageTitle','Nebula',box='[29,795][1051,909]'),n('categoryImageAuthor','Uploaded by: PublicBot',box='[68,909][609,962]'),n('categoryImageTitle','Park',box='[29,1482][1051,1596]'),n('categoryImageAuthor','Uploaded by: PublicAuthor',box='[68,1596][455,1649]')]
def test_public_credit_is_paired_with_its_caption():assert h.entries(feed())['images']==[{'caption':'Nebula','credit':'Uploaded by: PublicBot'},{'caption':'Park','credit':'Uploaded by: PublicAuthor'}]
def test_wrong_tab_does_not_masquerade_as_featured():
    ns=feed();ns[1]['selected']='false'
    with pytest.raises(ValueError):h.entries(ns)
def test_detail_page_refuses_gallery_read_even_with_underlying_feed():
    with pytest.raises(ValueError):h.entries(feed()+[n('mediaDetailTitle','Public image')])
def test_missing_credit_cannot_borrow_other_card_credit():
    ns=feed();del ns[4]
    with pytest.raises(ValueError):h.entries(ns)
def test_slight_native_text_overlap_still_pairs_same_card():
    ns=feed();ns[3]['bounds']='[29,886][1015,947]';ns[4]['bounds']='[68,942][440,995]';assert h.entries(ns)['images'][0]['caption']=='Nebula'
def test_foreign_focus_receives_no_input():
    class Device:
        def adb(self,*args):return 'mCurrentFocus=Window{abcd u0 foreign.app/.Main}'
        def tap(self,*args):raise AssertionError('Unexpected input')
    with pytest.raises(ValueError):h.tap(Device(),n('skip_login'))
def test_unknown_scroll_direction_refused_before_device_access():
    with pytest.raises(ValueError):h.scroll_featured(object(),{'direction':'sideways'},None)
