// Unit tests for the Skill Hub site libs. Run: npm run test:unit (node --test).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { wilsonLower, displayRating, normalizeTier, TIERS, CATEGORIES, MAX_POINTS, SCORING, normalizeScoring, assertScoring, categoryPoints } from '../../src/lib/hub/scoring.ts';
import { renderMarkdown } from '../../src/lib/hub/render.ts';

test('wilson lower bound matches the reference values', () => {
	assert.equal(wilsonLower(0, 0), 0);
	assert.ok(Math.abs(wilsonLower(180, 200) - 0.8506) < 1e-3);
	// 3/3 must rank below 180/200: the whole point of sorting on the lower bound
	assert.ok(wilsonLower(3, 3) < wilsonLower(180, 200));
	assert.ok(displayRating(20, 20) < 1 && displayRating(20, 20) > displayRating(10, 20));
});

test('ladder and caps come from the scoring file and total 100', () => {
	assert.deepEqual(TIERS.map((t) => t.id), ['draft', 'runs', 'proven', 'hardened', 'reference']);
	assert.deepEqual(TIERS.map((t) => t.points), TIERS.map((t) => SCORING.thresholds[t.id]));
	assert.deepEqual(TIERS.map((t) => t.points), [0, 10, 35, 60, 90]);
	assert.deepEqual(Object.fromEntries(CATEGORIES.map((c) => [c.id, c.cap])),
		{ docs: 20, self_evidence: 30, independent: 30, community_usage: 10, maintenance: 10 });
	assert.equal(CATEGORIES.reduce((n, c) => n + c.cap, 0), MAX_POINTS);
	assert.equal(normalizeTier('verified'), 'proven');
	assert.equal(normalizeTier('Hardened'), 'hardened');
	assert.equal(normalizeTier('C'), 'draft');
});

test('scoring file shapes normalise and bad files fail the build', () => {
	const tiers = { draft: 0, runs: 10, proven: 35, hardened: 65, reference: 90 };
	const flat = normalizeScoring({ caps: { docs: 15, self_evidence: 15, independent: 40, community_usage: 20, maintenance: 10 }, thresholds: tiers }, 'fixture', 'flat');
	const list = normalizeScoring({ categories: [{ id: 'docs', cap: 15, manifest: 3 }, { id: 'rest', cap: 85 }], tiers: Object.entries(tiers).map(([id, points]) => ({ id, points })) }, 'fixture', 'list');
	assert.doesNotThrow(() => assertScoring(flat));
	assert.doesNotThrow(() => assertScoring(list));
	assert.deepEqual(list.categories[0].items, [['manifest', 3]]);
	assert.throws(() => assertScoring(normalizeScoring({ categories: { docs: 15, independent: 35 }, tiers }, 'fixture', 'bad')), /sum to 50, must be 100/);
	assert.throws(() => assertScoring(normalizeScoring({ categories: { a: 100 }, tiers: { ...tiers, hardened: 30 } }, 'fixture', 'bad')), /must rise/);
	assert.throws(() => assertScoring(normalizeScoring({ categories: { a: 100 }, tiers: { draft: 0, runs: 10 } }, 'fixture', 'bad')), /missing/);
	assert.equal(categoryPoints({ usage: 7 }, 'community_usage'), 7);   // pre-0-100 registry key
	assert.equal(categoryPoints({ community_usage: 9, usage: 7 }, 'community_usage'), 9);
});

test('README rendering strips script, handlers and javascript: links', async () => {
	const html = await renderMarkdown('# Hi\n\n<script>alert(1)</script>\n<img src="x" onerror="alert(1)">\n\n<a href="javascript:alert(1)">x</a>\n\n<iframe src="https://e.vil"></iframe>');
	assert.ok(!/<script|onerror|javascript:|<iframe/i.test(html), html);
	assert.match(html, /<h1>Hi<\/h1>/);
	const ids = await renderMarkdown('<a id="q" name="main">x</a>');
	assert.match(ids, /id="readme-q"/); // author ids cannot clobber page ids
});

test('relative README URLs are rebased onto the published skill dir', async () => {
	const html = await renderMarkdown('![demo](demo.gif) [yaml](./skill.yaml) [abs](https://a.b/c) [anchor](#x)', {
		assets: 'https://cdn.jsdelivr.net/gh/o/r@a/s-v1/skillhub/a/s', links: 'https://github.com/o/r/tree/a/s-v1/skillhub/a/s',
	});
	assert.match(html, /src="https:\/\/cdn\.jsdelivr\.net\/gh\/o\/r@a\/s-v1\/skillhub\/a\/s\/demo\.gif"/);
	assert.match(html, /href="https:\/\/github\.com\/o\/r\/tree\/a\/s-v1\/skillhub\/a\/s\/skill\.yaml"/);
	assert.match(html, /href="https:\/\/a\.b\/c"/);
	assert.match(html, /href="#x"/);
});

test('generated validator runs under plain Node and enforces the D6 enums', async () => {
	const { default: validate } = await import('../../src/lib/hub/skill.validate.generated.js');
	const base = {
		name: 'x', version: '1.0.0', license: 'MIT', generated_with: 'hand',
		actions: [{ name: 'a', ref_prompt: 'do a', steps: [{ action: 'tap' }], end_state_validator: { kind: 'text_visible' } }],
	};
	assert.equal(validate(base), true, JSON.stringify(validate.errors));
	assert.equal(validate({ ...base, tos_risk: 'extreme' }), false);
	assert.equal(validate({ ...base, side_effects: ['sends_email'] }), false);
	assert.equal(validate({ ...base, license: '' }), false); // minLength goes through ajv's ucs2length runtime helper
	assert.equal(validate({ ...base, fingerprint: { os: 'android', theme: 'sepia' } }), false);
});

test('scoring v1.3 items render with labels and the per-action reliability rule', () => {
	const docs = CATEGORIES.find((c) => c.id === 'docs');
	const self = CATEGORIES.find((c) => c.id === 'self_evidence');
	assert.ok(docs.items.some(([label, pts]) => /Before \/ after/.test(label) && pts === '+3'));
	assert.ok(self.items.some(([label, pts]) => /Second device/.test(label) && pts === '+4'));
	assert.ok(self.items.some(([, rule]) => /once 3 exist on every action/.test(rule)));
});
