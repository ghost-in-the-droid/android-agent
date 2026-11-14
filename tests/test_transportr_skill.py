"""Public-station selection, window ownership and complete route rows."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('transportr_helper',Path(__file__).parents[1]/'skillhub/ghost/transportr/helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
@pytest.mark.parametrize('value',['x','a; input keyevent HOME','$(hostname)','https://example.org','a'*81])
def test_station_parameters_are_bounded_plain_names(value):
    with pytest.raises(ValueError):h.text_param(value)
def test_unowned_popup_is_not_allowed():
    class Device:
        def adb(self,*args):return 'mCurrentFocus=Window{abcd u0 PopupWindow:ff}\n  Window #1 Window{abcd u0 PopupWindow:ff}\n mOwnerUid=10000 package=foreign.app'
    with pytest.raises(ValueError):h.foreground(Device())
def test_expected_app_popup_requires_matching_window_token():
    class Device:
        def adb(self,*args):return 'mCurrentFocus=Window{abcd u0 PopupWindow:ff}\n  Window #1 Window{eeee u0 PopupWindow:ff}\n mOwnerUid=10000 package=de.grobox.liberario'
    with pytest.raises(ValueError):h.foreground(Device())
def test_nonempty_station_field_is_not_overtyped():
    class Device:
        def tap(self,*args):raise AssertionError('Must reject first')
    with pytest.raises(ValueError):h.choose(Device(),{'text':'Some other station'},'Berlin Alexanderplatz','S+U Alexanderplatz Bhf')
def n(rid,text,y):return {'resource-id':h.PKG+':id/'+rid,'text':text,'bounds':f'[23,{y}][300,{y+50}]','class':'android.widget.TextView'}
def test_departure_cannot_borrow_destination_from_next_row():
    ns=[n('departureTimeRel','now',250),n('line','S3',260),n('departureTimeAbs','10:00 AM',330),n('departureTimeRel','in 2min',500),n('destinationView','Next row destination',590)]
    assert h.rows_by_start(ns,'departureTimeRel',{'service':'line','destination':'destinationView','departure':'departureTimeAbs'})==[]
def test_equal_route_endpoints_rejected_before_device_input():
    with pytest.raises(ValueError,match='distinct'):h.search_connections(object(),dict(origin_query='Berlin',origin_station='Berlin',destination_query='Berlin',destination_station='Berlin'),None)
