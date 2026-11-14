// Unit tests for the reliability card data (evidence.ts), the bench card data
// (bench.ts) and the reference-skill rule (registry.ts). Run: npm run test:unit.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { summarizeEvidence, isEvidence, readEvidence, ageLabel } from '../../src/lib/hub/evidence.ts';
import { normalizeBench, fmtDelta, fmtWall, rate } from '../../src/lib/hub/bench.ts';
import { isReferenceSkill } from '../../src/lib/hub/reference.ts';

const SIG = { algorithm: 'ssh-ed25519', namespace: 'ghost-skill-run', public_key: 'ssh-ed25519 AAAA', value: '-----BEGIN SSH SIGNATURE-----' };
const fp = (hw, app) => ({ os: 'android', os_version: '14', hardware: hw, app_package: 'org.example', app_version: app });
function run({ when, ok = true, hash = 'aaaa', hw = 'Google/sdk_gphone64_x86_64', app = '1.4.0', actions, sim = false, backend = 'device', signed = true, verifier }) {
	return {
		artifact: {
			schema_version: 1, kind: verifier ? 'verification' : 'self-run', skill: 'a/s', version: '1.0.0',
			fingerprint: fp(hw, app), fingerprint_hash: hash, app_version: app, device_class: `${hw}/14`,
			timestamp: when, finished_at: when, success: ok,
			actions: actions ?? [{ name: 'calc', success: ok, duration_ms: 1000, error_kind: ok ? null : 'timeout', steps: [] }],
			device_backend: backend, simulation: sim, signature: signed ? SIG : undefined, verifier,
		},
		independent: !!verifier,
	};
}

test('evidence gate: unsigned and simulated artifacts never count', () => {
	assert.equal(isEvidence(run({ when: '2026-10-01T00:00:00Z' }).artifact), 'ok');
	assert.equal(isEvidence(run({ when: '2026-10-01T00:00:00Z', signed: false }).artifact), 'unsigned');
	assert.equal(isEvidence(run({ when: '2026-10-01T00:00:00Z', sim: true }).artifact), 'simulated');
	assert.equal(isEvidence(run({ when: '2026-10-01T00:00:00Z', backend: 'fake' }).artifact), 'simulated');
	const r = summarizeEvidence([
		run({ when: '2026-10-01T00:00:00Z' }),
		run({ when: '2026-10-02T00:00:00Z', sim: true }),
		run({ when: '2026-10-03T00:00:00Z', signed: false }),
	], ['calc'], 2);
	assert.equal(r.total, 1);
	assert.deepEqual(r.excluded, { simulated: 1, unsigned: 1, invalid: 2 });
	assert.equal(r.lastRun, '2026-10-01T00:00:00.000Z'); // the excluded, newer runs do not move it
});

test('per-action rows split self and independent and keep the newest run first', () => {
	const r = summarizeEvidence([
		run({ when: '2026-10-01T00:00:00Z', actions: [{ name: 'calc', success: true, duration_ms: 900 }, { name: 'read', success: false, duration_ms: 50, error_kind: 'element_missing' }] }),
		run({ when: '2026-10-05T00:00:00Z', app: '1.5.0', actions: [{ name: 'calc', success: true, duration_ms: 1100 }] }),
		run({ when: '2026-10-03T00:00:00Z', ok: false, hash: 'bbbb', hw: 'samsung/SM-A156', verifier: 'someoneelse', actions: [{ name: 'calc', success: false, duration_ms: 3000, error_kind: 'timeout' }, { name: 'ghost', success: true, duration_ms: 1 }] }),
	], ['calc', 'read']);
	assert.equal(r.total, 3); assert.equal(r.passed, 2);
	assert.deepEqual(r.self, { passed: 2, total: 2 });
	assert.deepEqual(r.independent, { passed: 0, total: 1 });
	assert.deepEqual(r.verifiers, ['someoneelse']);
	assert.equal(r.lastRun, '2026-10-05T00:00:00.000Z');
	assert.deepEqual(r.appVersions, ['1.5.0', '1.4.0']); // newest run's version first
	assert.deepEqual(r.actions.map((a) => a.action), ['calc', 'read']); // skill action order, unknown "ghost" dropped
	const calc = r.actions[0];
	assert.equal(calc.total, 3); assert.equal(calc.passed, 2);
	assert.deepEqual(calc.independent, { passed: 0, total: 1 });
	assert.equal(calc.medianMs, 1000); // median of passing durations only
	assert.deepEqual(calc.errorKinds, ['timeout']);
	const read = r.actions[1];
	assert.deepEqual([read.passed, read.total], [0, 1]);
	assert.deepEqual(read.errorKinds, ['element_missing']);
	assert.equal(read.medianMs, null);
	// fingerprints: independent first, each with its own pass count
	assert.deepEqual(r.fingerprints.map((f) => [f.hash, f.independent, f.passed, f.runs]), [['bbbb', true, 0, 1], ['aaaa', false, 2, 2]]);
	assert.deepEqual(r.fingerprints[1].appVersions, ['1.5.0', '1.4.0']);
});

test('readEvidence walks runs/ and verifications/ and treats the author as self', () => {
	const dir = mkdtempSync(join(tmpdir(), 'hub-evidence-'));
	mkdirSync(join(dir, 'runs')); mkdirSync(join(dir, 'verifications'));
	writeFileSync(join(dir, 'runs', 'aaaa-20261001T000000Z.json'), JSON.stringify(run({ when: '2026-10-01T00:00:00Z' }).artifact));
	writeFileSync(join(dir, 'runs', 'broken.json'), '{not json');
	writeFileSync(join(dir, 'runs', 'notes.txt'), 'ignored');
	const v = run({ when: '2026-10-02T00:00:00Z', hash: 'cccc', hw: 'pixel/7' }).artifact; delete v.verifier; delete v.fingerprint_hash;
	writeFileSync(join(dir, 'verifications', 'Alice-cccc-20261002T000000Z.json'), JSON.stringify(v));
	writeFileSync(join(dir, 'verifications', 'ghost-dddd-20261003T000000Z.json'), JSON.stringify({ ...v, fingerprint_hash: 'dddd', verifier: 'Ghost' }));
	const r = readEvidence(dir, 'ghost', ['calc']);
	assert.equal(r.total, 3);
	assert.deepEqual(r.independent, { passed: 1, total: 1 }); // Alice counts, the author's own verification does not
	assert.deepEqual(r.self, { passed: 2, total: 2 });
	assert.equal(r.excluded.invalid, 1);
	assert.deepEqual(r.verifiers, ['Alice']);
	assert.ok(r.fingerprints.some((f) => f.hash === 'cccc' && f.independent));
	assert.equal(readEvidence(join(dir, 'missing'), 'ghost', ['calc']).total, 0);
});

test('age labels', () => {
	const now = '2026-10-20T12:00:00Z';
	assert.equal(ageLabel(null, now), 'never');
	assert.equal(ageLabel('2026-10-20T01:00:00Z', now), 'today');
	assert.equal(ageLabel('2026-10-19T01:00:00Z', now), 'yesterday');
	assert.equal(ageLabel('2026-10-05T12:00:00Z', now), '15 days ago');
	assert.equal(ageLabel('2026-07-05T12:00:00Z', now), '3 months ago');
});

test('bench file normalises, drops bad rows and computes the delta', () => {
	const warnings = [];
	const b = normalizeBench({
		suite: 'androidworld', generated_at: '2026-10-21T00:00:00Z', upstream_commit: '2655e27cd090f97fbf2ccaecf759057bec0a8460', protocol: 'reports/androidworld-protocol.md',
		tasks: [
			{ task_id: 'ExpenseAddMultipleFromMarkor', action: 'add_expenses', seeds: 5, arms: { before: { passed: 2, total: 5, wall_ms_median: 312000, tokens_median: 41000 }, after_replay: { passed: 5, total: 5, wall_ms_median: 38000, tokens_median: 0 }, bogus: { passed: 1, total: 1 } } },
			{ task_id: 'MarkorMergeNotes', arms: { after_replay: { passed: 4, total: 5 } } },
			{ task_id: '../evil', arms: { before: { passed: 1, total: 1 } } },
			{ task_id: 'NoArms', arms: { before: { passed: 9, total: 5 } } },
		],
	}, (m) => warnings.push(m));
	assert.ok(b);
	assert.deepEqual(b.tasks.map((t) => t.task_id), ['ExpenseAddMultipleFromMarkor', 'MarkorMergeNotes']);
	assert.deepEqual(b.arms, ['before', 'after_replay']);
	assert.equal(b.tasks[0].delta, 0.6);
	assert.equal(b.tasks[1].delta, null); // no before arm, no delta
	assert.equal(b.tasks[0].action, 'add_expenses');
	assert.equal(b.upstreamCommit, '2655e27cd090f97fbf2ccaecf759057bec0a8460');
	assert.equal(warnings.length, 2);
	assert.equal(normalizeBench({ suite: 'other', tasks: [] }), null);
	assert.equal(normalizeBench({ suite: 'androidworld', tasks: [] }), null);
	assert.equal(normalizeBench({ suite: 'androidworld', protocol: 'javascript:alert(1)', tasks: [{ task_id: 'T', arms: { before: { passed: 1, total: 2 } } }] }).protocol, null);
	assert.deepEqual(fmtDelta(0.6), { text: '+60 pts', cls: 'delta-up' });
	assert.deepEqual(fmtDelta(-0.2), { text: '-20 pts', cls: 'delta-down' });
	assert.deepEqual(fmtDelta(0), { text: '±0', cls: 'delta-flat' });
	assert.equal(fmtDelta(null).text, '');
	assert.equal(rate({ passed: 1, total: 4 }), 0.25);
	assert.equal(fmtWall(38000), '38 s');
	assert.equal(fmtWall(312000), '5.2 min');
});

test('reference skills are the androidworld author namespace, nothing else', () => {
	assert.equal(isReferenceSkill({ author: 'androidworld' }), true);
	assert.equal(isReferenceSkill({ author: 'ghost' }), false);
	assert.equal(isReferenceSkill({ author: 'AndroidWorld' }), false); // handles are exact
});

test('scoring v1.1 structured items become readable rules and typed signals', async () => {
	const { normalizeScoring, assertScoring } = await import('../../src/lib/hub/scoring.ts');
	const tiers = { draft: 0, runs: 10, proven: 35, hardened: 65, reference: 90 };
	const cfg = normalizeScoring({
		version: 'v1.1',
		categories: {
			docs: { cap: 15, items: { manifest: 3 } },
			self_evidence: { cap: 15, items: { first_self_run: 3, validators: { each: 2, cap: 6, per: 'action', weights: { custom_python: 2, parameterised_text: 2, default: 1 } }, bench_one_model: 2, self_reliability: { cap: 4, min_runs: 10 } } },
			independent: { cap: 40 }, community_usage: { cap: 20 }, maintenance: { cap: 10 },
		},
		tiers,
	}, 'fixture', 'v11');
	assert.doesNotThrow(() => assertScoring(cfg));
	const se = cfg.categories.find((c) => c.id === 'self_evidence');
	assert.deepEqual(se.items, [['first_self_run', 3], ['bench_one_model', 2]]);
	assert.deepEqual(se.rules.map(([k]) => k), ['validators', 'self_reliability']);
	assert.match(se.rules[0][1], /\+2 each per action, up to \+6 \(weights: custom python x2, parameterised text x2, default x1\)/);
	assert.match(se.rules[1][1], /up to \+4, Wilson lower bound .* once 10 exist/);
	assert.deepEqual(cfg.selfReliability, { cap: 4, minRuns: 10 });
	assert.deepEqual(cfg.validatorRule, { each: 2, cap: 6, per: 'action', weights: { custom_python: 2, parameterised_text: 2, default: 1 } });
	// a v1 file has neither
	const v1 = normalizeScoring({ categories: { a: 100 }, tiers }, 'fixture', 'v1');
	assert.equal(v1.selfReliability, null);
	assert.equal(v1.validatorRule, null);
});

test('verifier tiers parse from verifier-keys.yml and decide maintainer vs independent', async () => {
	const { parseVerifierTiers } = await import('../../src/lib/hub/evidence.ts');
	const tiers = parseVerifierTiers(`version: 1\n# comment\nprincipals:\n  ghost:\n    tier: maintainer\n    keys:\n      - "ssh-ed25519 AAAA"\n  ghost-aw-replay:\n    tier: platform   # lab\n    operator: x\n  alice:\n    tier: community\n  bob:\n    keys: []\nother:\n  tier: platform\n`);
	assert.deepEqual(tiers, { ghost: 'maintainer', 'ghost-aw-replay': 'platform', alice: 'community', bob: 'community' });
	const r = summarizeEvidence([
		run({ when: '2026-10-20T00:00:00Z', hash: '91e3', hw: 'Google/sdk_gphone64_x86_64', verifier: 'ghost-aw-replay' }),
		run({ when: '2026-10-20T01:00:00Z', hash: '91e3', hw: 'Google/sdk_gphone64_x86_64', verifier: 'ghost-aw-replay' }),
		run({ when: '2026-10-21T00:00:00Z', hash: 'ab12', hw: 'samsung/SM-A156', verifier: 'alice' }),
		run({ when: '2026-10-19T00:00:00Z', hash: 'ab12', hw: 'samsung/SM-A156', verifier: 'alice', ok: false }),
	], ['calc'], 0, { verifierTiers: tiers, currentVersion: '1.0.0' });
	assert.deepEqual(r.maintainer, { passed: 2, total: 2 });
	assert.deepEqual(r.independent, { passed: 1, total: 2 });
	assert.deepEqual(r.self, { passed: 0, total: 0 });
	assert.equal(r.independentDevices, 1); // two alice runs, one fingerprint
	assert.equal(r.emulator, 2);
	assert.deepEqual(r.verifierTiers, { 'ghost-aw-replay': 'platform', alice: 'community' });
	const fps = Object.fromEntries(r.fingerprints.map((f) => [f.hash, [f.independent, f.maintainer, f.emulator]]));
	assert.deepEqual(fps, { ab12: [true, false, false], '91e3': [false, true, true] });
	// without tiers every verifier is independent (community)
	const r2 = summarizeEvidence([run({ when: '2026-10-20T00:00:00Z', verifier: 'ghost-aw-replay' })], ['calc']);
	assert.deepEqual(r2.independent, { passed: 1, total: 1 });
	assert.deepEqual(r2.maintainer, { passed: 0, total: 0 });
});

test('runs split into current and previous skill versions, emulator detected from the device model', async () => {
	const { looksLikeEmulator } = await import('../../src/lib/hub/evidence.ts');
	const a = run({ when: '2026-10-01T00:00:00Z' }).artifact; a.version = '1.0.0';
	const b = run({ when: '2026-10-02T00:00:00Z', hash: 'bb', hw: 'asus/ASUS_I002D' }).artifact; b.version = '1.0.2';
	const r = summarizeEvidence([{ artifact: a, independent: false }, { artifact: b, independent: false }], ['calc'], 0, { currentVersion: '1.0.2' });
	assert.deepEqual(r.currentVersion, { passed: 1, total: 1 });
	assert.deepEqual(r.previousVersion, { passed: 1, total: 1 });
	assert.equal(r.emulator, 1);
	assert.equal(looksLikeEmulator({ fingerprint: { hardware: 'Google/sdk_gphone64_x86_64' } }), true);
	assert.equal(looksLikeEmulator({ device_class: 'generic_x86/13' }), true);
	assert.equal(looksLikeEmulator({ fingerprint: { hardware: 'samsung/SM-A156' } }), false);
	// no currentVersion given: neither bucket is filled
	const r2 = summarizeEvidence([{ artifact: a, independent: false }], ['calc']);
	assert.deepEqual([r2.currentVersion.total, r2.previousVersion.total], [0, 0]);
});

test('confidence floor is the prior-free Wilson bound and the split copy uses raw counts', async () => {
	const { confidenceFloor, displayRating, wilsonLower } = await import('../../src/lib/hub/scoring.ts');
	const { runSplit, passedOverRuns } = await import('../../src/lib/hub/evidence.ts');
	assert.equal(confidenceFloor(3, 3), '44%');
	assert.equal(confidenceFloor(32, 32), '89%');
	assert.equal(confidenceFloor(0, 0), null);
	assert.ok(Math.abs(displayRating(32, 32) - wilsonLower(42, 52)) < 1e-12); // the tie-break keeps its prior, and is never shown
	const runs = { passed: 3, total: 3, emulator: { passed: 3, total: 3, unknown: 0 }, classes: { self: { passed: 0, total: 0 }, maintainer: { passed: 3, total: 3 }, ci: { passed: 0, total: 0 }, independent: { passed: 0, total: 0 } } };
	assert.equal(runSplit(runs), '3 runs: 0 self-recorded, 3 maintainer-signed replays, 0 independent (3 on an emulator).');
	assert.equal(passedOverRuns(runs), '3/3');
	assert.equal(passedOverRuns({ passed: 0, total: 0 }), 'no runs');
});

test('normalizeRuns: honest-signals registry block wins, pre-contract registry falls back to the artifacts', async () => {
	const { normalizeRuns } = await import('../../src/lib/hub/evidence.ts');
	const disk = summarizeEvidence([
		run({ when: '2026-10-20T00:00:00Z', hash: '91e3', verifier: 'ghost-aw-replay' }),
		run({ when: '2026-10-07T00:00:00Z', hash: 'aaaa' }),
	], ['calc'], 0, { verifierTiers: { 'ghost-aw-replay': 'platform' }, currentVersion: '1.0.2' });
	// contract-shaped block (reports/honest-signals.md)
	const contract = normalizeRuns({
		runs: {
			current_version: '1.0.2', passed: 0, total: 0, passed_90d: 0, total_90d: 0,
			self: { passed: 0, total: 0 }, maintainer: { passed: 0, total: 0 }, ci: { passed: 0, total: 0 }, independent: { passed: 0, total: 0 },
			previous_versions: { passed: 32, total: 32 }, emulator: { passed: 0, total: 0, unknown: 0 }, independent_devices: 0,
			verifiers: [{ principal: 'ghost-aw-replay', tier: 'platform', class: 'maintainer', label: 'AndroidWorld deterministic replay on the lab emulator', passed: 3, total: 3 }, { bogus: true }],
			rejected: { total: 1, reasons: { unsigned: 1, simulated: 0 } }, bench: 3,
		},
		signals: { runs_self_total: 99 },
	}, disk);
	assert.equal(contract.classesSource, 'registry');
	assert.deepEqual([contract.passed, contract.total], [0, 0]);
	assert.deepEqual(contract.previousVersions, { passed: 32, total: 32 });
	assert.deepEqual(contract.classes.self, { passed: 0, total: 0 }); // the runs block wins over signals
	assert.equal(contract.currentVersion, '1.0.2');
	assert.deepEqual(contract.verifiers, [{ principal: 'ghost-aw-replay', tier: 'platform', class: 'maintainer', label: 'AndroidWorld deterministic replay on the lab emulator', passed: 3, total: 3 }]);
	assert.deepEqual(contract.rejected, { total: 1, reasons: { unsigned: 1 } });
	assert.equal(contract.bench, 3);
	// signals-only variant of the contract
	const sigOnly = normalizeRuns({ runs: { passed: 1, total: 1 }, signals: { runs_maintainer_total: 1, runs_maintainer_passed: 1, runs_previous_total: 4, runs_previous_passed: 3, runs_emulator_total: 1, independent_devices: 0 } }, disk);
	assert.equal(sigOnly.classesSource, 'registry');
	assert.deepEqual(sigOnly.classes.maintainer, { passed: 1, total: 1 });
	assert.deepEqual(sigOnly.previousVersions, { passed: 3, total: 4 });
	assert.equal(sigOnly.emulator.total, 1);
	// pre-contract registry: totals from the registry, classes from disk (maintainer key never independent)
	const legacy = normalizeRuns({ runs: { passed: 2, total: 2, self: { passed: 1, total: 1 }, independent: { passed: 1, total: 1 }, rejected: { total: 0, reasons: {} }, bench: 0 }, signals: { independent_runs: 1, independent_device_classes: 1 } }, disk);
	assert.equal(legacy.classesSource, 'artifacts');
	assert.deepEqual([legacy.passed, legacy.total], [2, 2]);
	assert.deepEqual(legacy.classes.maintainer, { passed: 1, total: 1 });
	assert.deepEqual(legacy.classes.independent, { passed: 0, total: 0 });
	assert.deepEqual(legacy.classes.self, { passed: 1, total: 1 });
	assert.deepEqual(legacy.previousVersions, { passed: 2, total: 2 }); // both fixture runs are version 1.0.0, current is 1.0.2
	assert.equal(legacy.verifiers[0].class, 'maintainer');
	assert.equal(legacy.emulator.total, 2);
	assert.equal(legacy.independentDevices, 1); // the registry's own (pre-contract) number is kept
});

test('bench v2 (real ab1 fixture): valid re-run arms stay next to void ones, episodes, stats, calls headline', async () => {
	const { normalizeBench } = await import('../../src/lib/hub/bench.ts');
	const { readFileSync } = await import('node:fs');
	const warnings = [];
	const b = normalizeBench(JSON.parse(readFileSync(new URL('../fixtures/bench-androidworld-v2.json', import.meta.url), 'utf8')), (m) => warnings.push(m));
	assert.ok(b);
	assert.deepEqual(warnings, []);
	assert.equal(b.hasEpisodes, true);
	assert.deepEqual(b.arms, ['before', 'after_replay', 'after_mcp']);
	const t = b.tasks[0];
	assert.equal(t.task_id, 'ExpenseAddMultipleFromMarkor');
	// the ab1 re-run arms are valid and stay; the earlier void measurements are listed, never counted
	assert.deepEqual(Object.fromEntries(Object.entries(t.arms).map(([k, v]) => [k, [v.passed, v.total]])), { before: [0, 3], after_replay: [3, 3], after_mcp: [3, 3] });
	assert.deepEqual(t.voidArms.map((v) => [v.arm, v.total]), [['before', 3], ['after_mcp', 2]]);
	assert.match(t.voidArms[0].reason, /uninstalled/);
	assert.equal(t.delta, 1); // after_replay 3/3 minus before 0/3
	// episodes: 3 replay + 3 before + 3 after_mcp, all valid, replay rows have no model and no trace
	assert.equal(t.episodes.length, 9);
	assert.deepEqual(t.episodes.filter((e) => e.arm === 'after_replay').map((e) => [e.model, e.trace, e.llmCalls, e.skillCalls]), [[null, null, 0, 1], [null, null, 0, 1], [null, null, 0, 1]]);
	const mcp30 = t.episodes.find((e) => e.arm === 'after_mcp' && e.seed === 30);
	assert.deepEqual([mcp30.pass, mcp30.llmCalls, mcp30.tokens, mcp30.tokensCacheRead, mcp30.uiActions.total, mcp30.trace], [true, 11, 594883, 519400, 4, 'reports/agent-arm/ab1/after_mcp-30.jsonl']);
	assert.equal(mcp30.calls.length, 11);
	assert.equal(mcp30.calls[0].tokens_out, null); // null by design: the stream gives only the first chunk
	assert.ok(mcp30.actions.every((a) => /^(tap|type|swipe|key|launch|read|wait|skill)$/.test(a.type)));
	const before30 = t.episodes.find((e) => e.arm === 'before' && e.seed === 30);
	assert.deepEqual([before30.pass, before30.llmCalls, before30.uiActions.total], [false, 25, 22]);
	// calls headline: medians over valid episodes, before 25/25/25 -> 25, after_mcp 11/4/9 -> 9
	assert.deepEqual(t.callsHeadline, { before: 25, after: 9 });
	// stats: Wilson CI per arm and the paired McNemar block
	assert.deepEqual(t.stats.arms.after_mcp.wilson95, [0.4385, 1.0]);
	assert.deepEqual(t.stats.arms.after_mcp.models, ['claude-haiku-5-5']);
	assert.equal(t.stats.arms.after_mcp.llmCallsMedian, 9);
	assert.deepEqual(t.stats.paired, [{ key: 'after_mcp_vs_before', pairs: 3, onlyBeforePassed: 0, onlyAfterPassed: 3, mcnemarExactP: 0.25, tokensSavedMedian: 2057001 }]);
});

test('bench v2 edge cases: per-arm valid:false, bogus episode fields, path escapes, void-only tasks', async () => {
	const { normalizeBench } = await import('../../src/lib/hub/bench.ts');
	const b = normalizeBench({ suite: 'androidworld', tasks: [
		{ task_id: 'T', arms: { before: { passed: 0, total: 3, valid: false, invalid_reason: 'x' }, after_replay: { passed: 3, total: 3 } },
			episodes: [
				{ arm: 'before', seed: 1, model: 'm', pass: false, valid: false, invalid_reason: 'app gone', llm_calls: 9 },
				{ arm: 'before', seed: 2, model: 'm', pass: true, llm_calls: 7, trace: '../escape.jsonl', actions: [{ i: 1, type: 'bogus type!' }, { i: 2, type: 'tap', tool: 'tap_element', ok: true }] },
				{ arm: 'after_mcp', seed: 2, model: 'm', pass: true, calls: [{ i: 1, tokens_in: 1 }, { i: 2 }] },
				{ arm: 'nonsense', seed: 1, pass: true },
			], stats: { arms: { before: { wilson95: ['a', 1] } }, paired: { 'bad key': {}, after_mcp_vs_before: { pairs: 1, only_after_passed: 1 } } } },
		{ task_id: 'OnlyVoid', void_arms: { before: { passed: 0, total: 3, valid: false, invalid_reason: 'emulator died' } } },
		{ task_id: '../evil', arms: { before: { passed: 1, total: 1 } } },
	] });
	const t = b.tasks[0];
	assert.deepEqual(Object.keys(t.arms), ['after_replay']);
	assert.deepEqual(t.voidArms, [{ arm: 'before', total: 3, reason: 'x' }]);
	assert.equal(t.delta, null);
	assert.equal(t.episodes.length, 3);
	assert.deepEqual([t.episodes[0].valid, t.episodes[0].invalidReason], [false, 'app gone']);
	assert.equal(t.episodes[1].trace, null);
	assert.deepEqual(t.episodes[1].actions.map((a) => a.type), ['tap']);
	assert.equal(t.episodes[2].llmCalls, 2); // derived from calls[] when llm_calls is absent
	assert.deepEqual(t.callsHeadline, { before: 7, after: 2 }); // the invalid before episode (9) is excluded
	assert.equal(t.stats.arms.before.wilson95, null);
	assert.deepEqual(t.stats.paired, [{ key: 'after_mcp_vs_before', pairs: 1, onlyBeforePassed: 0, onlyAfterPassed: 1, mcnemarExactP: null, tokensSavedMedian: null }]);
	assert.deepEqual(b.tasks.map((x) => x.task_id), ['T', 'OnlyVoid']);
	assert.deepEqual(Object.keys(b.tasks[1].arms), []);
	assert.equal(b.tasks[1].voidArms[0].reason, 'emulator died');
});
