// Before / after pair numbers: validation and the plain-language summary shown on skill pages and the hub list.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatRatio, formatSeconds, normalizeBeforeAfter, summarizeBeforeAfter } from '../../src/lib/hub/before-after.ts';

const base = {
	schema_version: 1, action: 'generate_qr', prompt: 'Generate a QR code', ok_means: 'verified_task_check',
	before: { seconds: 52.24, tokens: 254235, tool_calls: 18, ok: false },
	after: { seconds: 27.49, tokens: 21500, tool_calls: 5, ok: true },
	notes: 'same clean app per side',
};

test('ratios round the way the page reads them', () => {
	assert.equal(formatRatio(11.76), '11.8×');
	assert.equal(formatRatio(4.02), '4×');
	assert.equal(formatRatio(23.4), '23×');
	assert.equal(formatRatio(0), '–');
	assert.equal(formatSeconds(52.24), '52.2 s');
	assert.equal(formatSeconds(202.12), '202 s');
});

test('summary states fewer tokens and faster with the verified outcome', () => {
	const s = summarizeBeforeAfter(normalizeBeforeAfter(base));
	assert.equal(s.tokens, '11.8× fewer tokens');
	assert.equal(s.time, '1.9× faster');
	assert.equal(s.calls, '18 → 5 tool calls');
	assert.equal(s.headline, '11.8× fewer tokens, 1.9× faster');
	assert.equal(s.outcome, 'Task check: failed without the skill, passed with it.');
	assert.ok(s.tokensFewer && s.faster);
});

test('summary never flatters: slower runs and more tokens are said as such', () => {
	const slower = normalizeBeforeAfter({ ...base, before: { seconds: 9.73, tokens: 12504, tool_calls: 3, ok: false }, after: { seconds: 18.39, tokens: 21000, tool_calls: 3, ok: true } });
	const s = summarizeBeforeAfter(slower);
	assert.equal(s.tokens, '1.7× more tokens');
	assert.equal(s.time, '1.9× slower');
	assert.equal(s.headline, '1.7× more tokens, 1.9× slower');
	assert.ok(!s.tokensFewer && !s.faster);
	const same = summarizeBeforeAfter(normalizeBeforeAfter({ ...base, after: { ...base.before, ok: true } }));
	assert.equal(same.headline, 'about the same tokens, about the same time');
});

test('finished-turn pairs say the result was not independently checked', () => {
	const s = summarizeBeforeAfter(normalizeBeforeAfter({ ...base, ok_means: 'agent_finished_turn', before: { ...base.before, ok: true } }));
	assert.equal(s.outcome, 'Agent run: finished without the skill, finished with it (not independently checked).');
	const stopped = summarizeBeforeAfter(normalizeBeforeAfter({ ...base, ok_means: 'agent_finished_turn' }));
	assert.match(stopped.outcome, /stopped early without the skill, finished with it/);
});

test('malformed numbers warn and drop to null instead of showing a wrong figure', () => {
	const warnings = [];
	const warn = (m) => warnings.push(m);
	assert.equal(normalizeBeforeAfter(null, warn), null);
	assert.equal(normalizeBeforeAfter({ ...base, schema_version: 2 }, warn), null);
	assert.equal(normalizeBeforeAfter({ ...base, after: { seconds: 1, tokens: 1 } }, warn), null);
	assert.equal(normalizeBeforeAfter({ ...base, before: { ...base.before, tokens: -1 } }, warn), null);
	assert.equal(normalizeBeforeAfter({ ...base, before: { ...base.before, ok: 'yes' } }, warn), null);
	assert.equal(normalizeBeforeAfter({ ...base, ok_means: 'vibes' }, warn), null);
	assert.equal(normalizeBeforeAfter('nope', warn), null);
	assert.deepEqual(warnings, [
		'schema_version must be 1', '`after.tool_calls` must be a number >= 0', '`before.tokens` must be a number >= 0',
		'`before.ok` must be true or false', 'ok_means must be one of verified_task_check, agent_finished_turn', 'must be an object',
	]);
	const ok = normalizeBeforeAfter({ ...base, model: '', device: 7, notes: null });
	assert.equal(ok.model, null); assert.equal(ok.device, null); assert.equal(ok.notes, null);
	assert.equal(ok.ok_means, 'verified_task_check');
});
