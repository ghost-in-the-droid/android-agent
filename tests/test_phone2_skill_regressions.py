"""Regressions found in real phone B comparison recordings; no device required."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def helper(slug):
    spec = importlib.util.spec_from_file_location(slug, ROOT / 'skillhub' / 'ghost' / slug / 'helpers.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def berlin_rows():
    return [
        {'name': 'Berlin', 'region': 'Germany, State of Berlin, Berlin, Stadt'},
        {'name': 'Berlin', 'region': 'United States, New Hampshire, Coos, City of Berlin'},
        {'name': 'Berlin', 'region': 'United States, New Jersey, Camden, Borough of Berlin'},
    ]


@pytest.mark.parametrize('params', [{}, {'country': 'United States'}, {'country': 'Canada'}, {'match': 'Canada'}])
def test_weather_ambiguous_or_unmatched_search_never_falls_back(params):
    h = helper('weather')
    hit, error = h.select_location(berlin_rows(), {'query': 'Berlin', **params})
    assert hit is None
    assert 'No location was saved' in error


@pytest.mark.parametrize('params,country', [
    ({'country': 'Germany'}, 'Germany'),
    ({'country': 'United States', 'region': 'New Hampshire'}, 'United States'),
    ({'match': 'Germany'}, 'Germany'),
])
def test_weather_selects_requested_country_and_region(params, country):
    h = helper('weather')
    hit, error = h.select_location(berlin_rows(), {'query': 'Berlin', **params})
    assert error is None
    assert h.country_of(hit) == country


def test_weather_does_not_drop_germany_row_above_old_pixel_cutoff():
    h = helper('weather')
    def node(text, x, y, bottom):
        return {'text': text, 'bounds': (x, y, x + 200, bottom)}
    nodes = [node('Berlin', 0, 80, 238), node('Berlin', 45, 280, 348),
             node('Germany, State of Berlin, Berlin, Stadt', 45, 348, 405),
             node('Berlin', 45, 494, 562), node('United States, New Hampshire', 45, 562, 619)]
    hit, error = h.select_location(h.search_rows(nodes), {'country': 'Germany'})
    assert error is None
    assert h.country_of(hit) == 'Germany'


def test_weather_validator_rejects_wrong_country_even_if_city_is_saved(monkeypatch):
    h = helper('weather')
    monkeypatch.setattr(h, 'visible_nodes', lambda _: [])
    monkeypatch.setattr(h, 'read_locations', lambda _: [{'name': 'Berlin'}])
    ctx = SimpleNamespace(params={'query': 'Berlin', 'country': 'Germany'}, result={
        'picked': {**berlin_rows()[1], 'country': 'United States'}})
    assert not h.location_listed(None, ctx)
    ctx.result['picked'] = {**berlin_rows()[0], 'country': 'Germany'}
    assert h.location_listed(None, ctx)


def test_fdroid_replaces_stale_query_instead_of_appending(monkeypatch):
    h = helper('fdroid')
    class SearchDevice:
        text = 'Connect Four'
        submitted = False
        def tap(self, *args): pass
        def adb(self, *args):
            if args[:3] == ('shell', 'input', 'text'):
                self.text += args[3]
            elif 'KEYCODE_DEL' in args:
                self.text = self.text[:-args.count('KEYCODE_DEL')]
            elif 'KEYCODE_ENTER' in args:
                self.submitted = True
    dev = SearchDevice()
    monkeypatch.setattr(h, 'visible_nodes', lambda _: [{'cls': 'android.widget.EditText', 'text': dev.text, 'bounds': (0, 80, 900, 200)}])
    result = h.enter_query(dev, {'query': 'Markor'}, None)
    assert result['success']
    assert dev.text == 'Markor'
    assert dev.submitted


@pytest.mark.parametrize('field,result_name', [('Connect Four', 'Markor'), ('Markor', 'Connect Four')])
def test_fdroid_validator_rejects_stale_query_or_unrelated_results(monkeypatch, field, result_name):
    h = helper('fdroid')
    monkeypatch.setattr(h, 'visible_nodes', lambda _: [{'cls': 'android.widget.EditText', 'text': field}])
    ctx = SimpleNamespace(params={'query': 'Markor'}, result={
        'query': 'Markor', 'results': [{'name': result_name, 'summary': 'Offline application'}]})
    assert not h.has_results(None, ctx)


def test_fdroid_results_do_not_require_apps_heading(monkeypatch):
    h = helper('fdroid')
    nodes = [
        {'cls': 'android.widget.EditText', 'text': 'Markor', 'bounds': (0, 80, 900, 200)},
        {'text': 'Markor', 'bounds': (210, 500, 500, 560)},
        {'text': 'Markdown editor', 'bounds': (210, 560, 800, 620)},
    ]
    monkeypatch.setattr(h, 'visible_nodes', lambda _: nodes)
    assert h.wait_for_results(None, {'query': 'Markor'}, None)['success']


def test_fdroid_xml_fallback_reads_editable_query_and_decodes_entities():
    h = helper('fdroid')
    dev = SimpleNamespace(dump_xml=lambda: '<hierarchy><node class="android.widget.EditText" text="notes &amp; tasks" bounds="[0,80][900,200]" /></hierarchy>')
    assert h.query_matches(h.visible_nodes(dev), 'notes & tasks')


def test_fdroid_waits_for_initial_import_before_search(monkeypatch):
    h = helper('fdroid')
    nav = {'text': 'Discover', 'desc': '', 'bounds': (0, 2100, 300, 2160)}
    loading = {'text': 'Fetching app repositories…', 'bounds': (45, 794, 1035, 862)}
    ready = {'text': 'Markor', 'bounds': (210, 500, 800, 560)}
    states = iter([[nav, loading], [nav, loading], [nav, ready]])
    seen = []
    def nodes(_):
        value = next(states)
        seen.append(value)
        return value
    monkeypatch.setattr(h, 'visible_nodes', nodes)
    monkeypatch.setattr(h, '_tap', lambda *_: None)
    monkeypatch.setattr(h.time, 'sleep', lambda _: None)
    assert h.wait_for_catalogue(None, {}, None)['success']
    assert seen[-1] == [nav, ready]


def test_fdroid_accepts_delayed_accessibility_navigation_description(monkeypatch):
    h = helper('fdroid')
    target = {'text': '', 'desc': 'Search', 'bounds': (400, 2100, 600, 2160)}
    states = iter([[], [target]])
    taps = []
    monkeypatch.setattr(h, 'visible_nodes', lambda _: next(states))
    monkeypatch.setattr(h, '_tap', lambda _, n: taps.append(n))
    monkeypatch.setattr(h.time, 'sleep', lambda _: None)
    assert h.open_search_tab(None, {}, None)['success']
    assert taps == [target]

def test_fdroid_waits_for_query_readback_before_enter(monkeypatch):
    h=helper('fdroid')
    class D:
        submitted=False
        def tap(self,*_):pass
        def adb(self,*args):
            if 'KEYCODE_ENTER' in args:self.submitted=True
    d=D();reads=iter(['Old query','Old query','Markor'])
    monkeypatch.setattr(h,'visible_nodes',lambda _:[{'cls':'android.widget.EditText','text':next(reads),'bounds':(0,80,900,200)}])
    monkeypatch.setattr(h.time,'sleep',lambda _:None)
    assert h.enter_query(d,{'query':'Markor'},None)['success'] and d.submitted
