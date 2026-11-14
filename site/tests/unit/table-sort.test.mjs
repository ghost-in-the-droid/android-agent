import { test } from 'node:test';
import assert from 'node:assert/strict';
import { nextSort, ariaSort, compareRows } from '../../src/lib/hub/table-sort.ts';

const row = (name, order, score, extra = {}) => ({ name, order, actions: 1, score, runs: 0, ...extra });

test('clicking a column sorts, clicking again toggles asc/desc, another column resets', () => {
 let s = { key: null, dir: 'desc' };
 s = nextSort(s, 'score');
 assert.deepEqual(s, { key: 'score', dir: 'desc' });
 s = nextSort(s, 'score');
 assert.deepEqual(s, { key: 'score', dir: 'asc' });
 s = nextSort(s, 'score');
 assert.deepEqual(s, { key: 'score', dir: 'desc' });
 assert.deepEqual(nextSort(s, 'name'), { key: 'name', dir: 'asc' });
});

test('aria-sort reflects only the active column', () => {
 const s = { key: 'score', dir: 'asc' };
 assert.equal(ariaSort(s, 'score'), 'ascending');
 assert.equal(ariaSort({ ...s, dir: 'desc' }, 'score'), 'descending');
 assert.equal(ariaSort(s, 'name'), 'none');
 assert.equal(ariaSort({ key: null, dir: 'desc' }, 'score'), 'none');
});

test('compareRows orders by the active column and direction, ties by name; no key keeps registry order', () => {
 const rows = [row('b/x', 0, 50), row('a/y', 1, 80), row('c/z', 2, 80)];
 const sorted = (s) => [...rows].sort((a, b) => compareRows(s, a, b)).map((r) => r.name);
 assert.deepEqual(sorted({ key: 'score', dir: 'desc' }), ['a/y', 'c/z', 'b/x']);
 assert.deepEqual(sorted({ key: 'score', dir: 'asc' }), ['b/x', 'a/y', 'c/z']);
 assert.deepEqual(sorted({ key: 'name', dir: 'desc' }), ['c/z', 'b/x', 'a/y']);
 assert.deepEqual(sorted({ key: null, dir: 'desc' }), ['b/x', 'a/y', 'c/z']);
});

test('run counts sort numerically and start highest first', () => {
 const a = row('a', 0, 1, { runs: 12 }), b = row('b', 1, 1, { runs: 4 });
 assert.deepEqual(nextSort({ key: null, dir: 'asc' }, 'runs'), { key: 'runs', dir: 'desc' });
 assert.ok(compareRows({ key: 'runs', dir: 'desc' }, a, b) < 0);
 assert.ok(compareRows({ key: 'runs', dir: 'asc' }, a, b) > 0);
});
