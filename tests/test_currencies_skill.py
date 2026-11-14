"""Currency keypad boundaries and literal numeric readback."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('currencies_helper',Path(__file__).parents[1]/'skillhub/ghost/currencies/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

@pytest.mark.parametrize('text',['$ 125+2','€ 1.2.3','£ 2×4','125/2','NaN','1,2,3'])
def test_pending_expression_is_not_a_fabricated_converted_amount(text):
    with pytest.raises(ValueError):h.number(text)

def test_grouped_display_keeps_exact_decimal_value():
    assert h.number('¥ 20,123.45')=='20123.45'
    assert h.number('£ 0')=='0'

@pytest.mark.parametrize('value',['-1','1e9','1+2','0.001','1234567890','001'])
def test_only_bounded_plain_keypad_amounts_allowed(value):
    with pytest.raises(ValueError):h.amount(value)

class Device:
    def __init__(self):self.inputs=[]
    def adb(self,*args):return 'mCurrentFocus=Window{abcd u0 other.app/.Main}'
    def tap(self,*args):self.inputs.append(args)

def test_stale_keypad_cannot_drive_another_app():
    d=Device()
    with pytest.raises(ValueError,match='focused window'):h.tap(d,{'bounds':'[0,300][100,400]'})
    assert not d.inputs

def test_currency_input_cannot_inject_adb_shell_text():
    d=Device()
    with pytest.raises(ValueError,match='uppercase'):h.select_source(d,{'currency':'GBP;input keyevent HOME'},None)
    assert not d.inputs
