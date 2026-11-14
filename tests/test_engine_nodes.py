"""Node parsing shared by read steps and future skill helpers."""
import pytest

from gitd.skills.engine.nodes import parse, by, centre
from gitd.skills.engine.dispatch import _all_nodes


def test_nested_nodes_order_entities_and_attributes():
    xml = ('<hierarchy><node text="A &amp; B" bounds="[0,1][10,20]" class="Container">'
           '<node text="child" content-desc="Open" resource-id="app:id/item" '
           'package="com.example" checked="true" bounds="[1,2][8,9]"/>'
           '</node><node text="last" bounds="[0,0][1,1]"/></hierarchy>')
    nodes = parse(xml)
    assert [n['text'] for n in nodes] == ['A &amp; B', 'child', 'last']
    child = by(nodes, 'id', 'app:id/item')[0]
    assert child['checked'] and child['package'] == 'com.example'
    assert by(nodes, 'desc', 'Open') == [child]
    assert by(nodes, 'text', 'Child') == []
    assert by(nodes, 'xpath', '//node') == []
    assert by(nodes, 'cls', 'Container') == [nodes[0]]
    assert centre(child) == (4, 5)
    assert centre(nodes[2]) == (0, 0)
    assert _all_nodes(xml, 'text', 'child') == [
        {key: child[key] for key in ('text', 'desc', 'id', 'bounds', 'checked')}
    ]


@pytest.mark.parametrize('bounds', ['', '[0,0][0,5]', '[0,2][5,2]', '[-1,0][5,5]',
                                    '[0,-1][5,5]', '[5,0][1,5]', '[0,0][5]', 'junk0,0,5,5'])
def test_invalid_or_offscreen_nodes_are_excluded(bounds):
    assert parse(f'<hierarchy><node text="bad" bounds="{bounds}"/></hierarchy>') == []


def test_empty_snapshot_and_no_mutation():
    assert parse('') == []
    assert parse('<hierarchy/>') == []
    original = parse('<node text="x" bounds="[0,0][5,5]"/>')
    matches = by(original, 'text', 'x')
    matches[0]['text'] = 'changed'
    assert original[0]['text'] == 'x'
