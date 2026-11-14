"""Food-label completeness and public-read-only input boundaries."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('food_helper',Path(__file__).parents[1]/'skillhub/ghost/open-food-facts/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
@pytest.mark.parametrize('query',['x','a; input keyevent HOME','$(hostname)','https://example.org','a'*61])
def test_query_rejects_commands_urls_and_unbounded_values(query):
    with pytest.raises(ValueError):h.term(query)
def n(desc,box='[90,547][984,659]',cls='android.widget.Button'):
    return {'content-desc':desc,'bounds':box,'class':cls}
def test_nutrients_require_all_four_visible_rows():
    ns=[n('Details for Nutrient levels with Nutella'),n('Fat in high quantity (30.9%)'),n('Saturated fat in high quantity (10.6%)'),n('Sugars in high quantity (56.3%)'),n('Salt in low quantity (0.107%)')]
    assert len(h.nutrients(ns)['nutrient_levels'])==4
    with pytest.raises(ValueError):h.nutrients(ns[:-1])
def test_foreign_app_receives_no_tap():
    class Device:
        def adb(self,*args):return 'mCurrentFocus=Window{abcd u0 foreign.app/.Main}'
        def tap(self,*args):raise AssertionError('Must refuse input')
    with pytest.raises(ValueError):h.tap(Device(),n('Authorize'))
def test_result_card_cannot_borrow_score_from_next_card():
    ns=[dict(text='nutella',bounds='[363,125][920,193]',**{'class':'android.widget.EditText'}),n('157 products (United States)',cls='android.view.View'),n('7% Nutella Nutella','[0,440][1080,834]','android.view.View'),n('Nutri-Score E (New calculation)','[349,1066][507,1173]','android.widget.ImageView')]
    assert h.cards(ns)==[]
def test_contribution_screen_cannot_receive_product_back(monkeypatch):
    monkeypatch.setattr(h,'nodes',lambda d:[n('Edit product'),n('Back')])
    class Device:
        def tap(self,*args):raise AssertionError('No navigation from unsupported screen')
    with pytest.raises(ValueError):h.back_to_results(Device(),{},None)
