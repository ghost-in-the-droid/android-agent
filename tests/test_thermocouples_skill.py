"""Reference records, exposed-tab limits and comparison final-state checks."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]/'skillhub/ghost/thermocouples'
spec=importlib.util.spec_from_file_location('thermocouple_helpers',ROOT/'helpers.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)


def node(rid='',text='',desc='',width=190):
    return {'id':h.ID+rid if rid else '', 'text':text,'desc':desc,'cls':'android.widget.LinearLayout',
            'bounds':(0,0,width,100),'package':h.PKG,'checked':False}


def reference(type_name='K',printed='-200 to 1250°C'):
    return [node('DetailsItem'),node('tcTitle','Type '+type_name),node('tcPositiveLeg','Nickel-Chromium'),
            node('tcNegativeLeg','Nickel-Aluminium'),node('tcTempRange',printed)]


def test_reference_preserves_displayed_units_and_metals():
    assert h.details(reference()) == dict(type='K',positive_metal='Nickel-Chromium',
        negative_metal='Nickel-Aluminium',printed_range_c='-200 to 1250°C',min_c=-200,max_c=1250)


@pytest.mark.parametrize('printed',['1250 to -200°C','100 to 100°C','-200 to 1250°F','? to 1250°C',''])
def test_missing_or_invalid_range_is_not_fabricated(printed):
    with pytest.raises(ValueError):h.details(reference(printed=printed))


def test_duplicate_field_does_not_choose_a_value():
    with pytest.raises(ValueError,match='unique'):h.details(reference()+[node('tcPositiveLeg','Other')])


def test_clipped_or_missing_type_tab_is_not_tapped():
    with pytest.raises(ValueError,match='fully exposed'):h.tab([node(desc='Type K',width=120)],'K')
    with pytest.raises(ValueError,match='fully exposed'):h.tab([],'K')


@pytest.mark.parametrize('params',[{'left':'K','right':'K'},{'left':'R','right':'E'},{}])
def test_comparison_requires_distinct_supported_types_before_device_use(params):
    with pytest.raises(ValueError,match='distinct'):h.compare_types(None,params,None)


def test_foreign_foreground_refuses_all_reads_and_entry():
    class D:
        def foreground_package(self):return 'com.example.foreign'
        def adb(self,*args):pytest.fail('must not launch')
        def dump_xml(self,**kwargs):pytest.fail('must not read')
    with pytest.raises(ValueError,match='unrelated'):h.open_app(D(),{},None)
    with pytest.raises(ValueError,match='foreground'):h.read_details(D(),{},None)


def test_comparison_validator_checks_last_native_record(monkeypatch):
    left=h.details(reference());right=h.details(reference('E','-200 to 900°C'))
    ctx=SimpleNamespace(params={'left':'K','right':'E'},result={'left':left,'right':right,'final_type':'E'})
    monkeypatch.setattr(h,'nodes',lambda d:reference('E','-200 to 900°C'))
    assert h.comparison_ok(None,ctx)
    monkeypatch.setattr(h,'nodes',lambda d:reference('K'))
    assert not h.comparison_ok(None,ctx)
