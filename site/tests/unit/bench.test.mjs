import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { normalizeBench, readBenches, passText, countedEpisode, fmtSkillVersion, labelledEpisodeOutcome } from '../../src/lib/hub/bench.ts';
import { pairedSavings, pooledPass, wilson, readShowcase, listedTasks, pooledMcNemar } from '../../src/lib/hub/showcase.ts';
const fixture = JSON.parse(readFileSync(new URL('../fixtures/bench-ghost-native-v2.json', import.meta.url), 'utf8'));

test('native fixture copies all calculator episodes and stats from nat2 without inventing measurements', () => {
 const source = JSON.parse(readFileSync(new URL('../fixtures/ab-nat2.json', import.meta.url), 'utf8'));
 assert.deepEqual(fixture.tasks[0].episodes, source.episodes.calc_3plus3);
 assert.deepEqual(fixture.tasks[0].stats, source.stats.tasks.find((t) => t.task_id === 'calc_3plus3'));
 const b = normalizeBench(fixture), t = b.tasks[0];
 assert.equal(b.evidenceClass, 'maintainer'); assert.equal(b.label, 'maintainer-run, not independent');
 assert.equal(b.model, 'claude-haiku-5-5'); assert.equal(b.source, 'reports/ab/nat2.json');
 assert.ok(b.generatedAt); assert.equal(t.label, 'Calculate 3 + 3'); assert.equal(t.action, 'calculate');
 assert.equal(t.episodes.length, 15); assert.equal(t.stats.arms.before.tokensQ1, 132498);
 assert.equal(t.stats.arms.before.tokensQ3, 267125); assert.equal(t.stats.arms.before.uiActionsMedian, 6);
 assert.equal(t.stats.arms.after_replay.llmCallsMedian, 0);
 assert.equal(pairedSavings(t).tokens, 123150); assert.equal(pairedSavings(t).tokenPairs, 5);
 assert.equal(pooledPass([t], 'after_mcp').total, 5);
 assert.match(passText(t.arms.before, t.stats.arms.before.wilson95), /^5\/5 · Wilson 95% CI/);
 assert.equal(passText(t.arms.before), '5/5 · no CI');
});

test('loader reads both suites, warns and skips unknown or broken files', () => {
 const dir = mkdtempSync(join(tmpdir(), 'bench-'));
 try {
  mkdirSync(join(dir, 'bench'));
  for (const [name, raw] of Object.entries({ native: fixture, android: { ...fixture, suite: 'androidworld', model: ['claude-haiku-5-5'] }, unknown: { ...fixture, suite: 'future' } })) writeFileSync(join(dir, 'bench', name + '.json'), JSON.stringify(raw));
  writeFileSync(join(dir, 'bench', 'broken.json'), '{');
  const warnings = [], benches = readBenches(dir, (m) => warnings.push(m));
  assert.deepEqual(benches.map((b) => b.suite), ['androidworld', 'ghost-native']);
  assert.equal(benches[0].model, 'claude-haiku-5-5'); assert.equal(warnings.length, 2);
  assert.deepEqual(readBenches(null), []);
 } finally { rmSync(dir, { recursive: true, force: true }); }
});

test('labelled episodes, including failures and void rows, are isolated from current results', () => {
 const raw = structuredClone(fixture);
 raw.tasks[0].source = 'reports/ab/nat2.json'; raw.tasks[0].generated_at = fixture.generated_at; raw.tasks[0].run_ids = ['nat2'];
 raw.tasks[0].labelled_results = { old_bug: { label: 'Pre-fix skill', model: 'claude-haiku-5-5', passed: 0, total: 1, episodes: [{ ...raw.tasks[0].episodes[0], pass: false }, { ...raw.tasks[0].episodes[1], valid: false, invalid_reason: 'budget cut' }] } };
 const task = normalizeBench(raw).tasks[0];
 assert.equal(task.labelledResults[0].label, 'Pre-fix skill');
 assert.equal(task.labelledResults[0].episodes[0].pass, false);
 assert.equal(task.labelledResults[0].episodes[1].invalidReason, 'budget cut');
 assert.equal(task.episodes.length, 15); assert.equal(task.arms.after_mcp.passed, 5);
 assert.equal(task.source, raw.tasks[0].source); assert.deepEqual(task.runIds, ['nat2']);
 assert.equal(pairedSavings(task).tokenPairs, 5); assert.equal(pooledPass([task], 'after_mcp').passed, 5);
});

test('malformed rows and unsafe paths cannot become results', () => {
 const raw = structuredClone(fixture); raw.source = '../secret';
 raw.tasks[0].arms.before = { passed: .5, total: 2 };
 raw.tasks[0].stats.arms.before.wilson95 = [1, -1];
 raw.tasks[0].episodes.push({ arm: 'before', seed: 12 }, null, { arm: 'unknown', pass: true });
 const b = normalizeBench(raw);
 assert.equal(b.source, null); assert.equal(b.tasks[0].arms.before, undefined);
 assert.equal(b.tasks[0].stats.arms.before.wilson95, null); assert.equal(b.tasks[0].episodes.length, 15);
 for (const x of [null, 5, [], {}, { suite: 'unknown' }]) assert.doesNotThrow(() => normalizeBench(x));
});

test('pairing excludes void rows, rejects duplicate seeds, and keeps zero savings', () => {
 const t = normalizeBench(fixture).tasks[0];
 t.episodes = [
  { arm: 'before', seed: 1, model: 'a', valid: true, tokens: 10, uiActions: { total: 2 } },
  { arm: 'after_mcp', seed: 1, model: 'a', valid: true, tokens: 10, uiActions: { total: 2 } },
  { arm: 'before', seed: 2, model: 'a', valid: true, tokens: 100 },
  { arm: 'after_mcp', seed: 4, model: 'b', valid: true, tokens: 0 },
  { arm: 'before', seed: 3, model: 'a', valid: false, tokens: 100 },
  { arm: 'after_mcp', seed: 3, model: 'a', valid: true, tokens: 0 },
 ];
 assert.deepEqual(pairedSavings(t), { tokens: 0, tokenPairs: 1, percent: 0, percentPairs: 1, actions: 0, actionPairs: 1 });
 t.episodes.push({ ...t.episodes[1] }); assert.throws(() => pairedSavings(t), /duplicate seed/);
 assert.equal(wilson(0, 0), null); assert.ok(Math.abs(wilson(5, 5)[0] - .5655) < .0001);
});


test('action coverage follows skill.yaml and accepts later benchmark rows without page changes', () => {
 const dir = mkdtempSync(join(tmpdir(), 'showcase-'));
 try {
  writeFileSync(join(dir, 'showcase.yml'), 'skills: [{ref: ghost/calculator, task: calc_3plus3}]');
  writeFileSync(join(dir, 'skill.yaml'), 'version: 2.0.0\nactions: [{name: calculate}, {name: new_action}]');
  const skill = { id: 'ghost/calculator', skillDir: dir, latest: 'old-registry', latestEntry: { actions: ['calculate'] }, benches: [] };
  const hub = { root: dir, skills: [skill] };
  let entry = readShowcase(hub)[0];
  assert.equal(entry.rows.length, 0); assert.equal(entry.covered, 0);
  assert.deepEqual(entry.actions, ['calculate', 'new_action']); assert.equal(entry.version, '2.0.0');
  skill.benches = [normalizeBench(fixture)];
  assert.equal(readShowcase(hub)[0].covered, 1);
  skill.benches[0].tasks.push({ ...skill.benches[0].tasks[0], action: 'new_action', task_id: 'later_task' });
  assert.equal(readShowcase(hub)[0].covered, 2);
 } finally { rmSync(dir, { recursive: true, force: true }); }
});


test('arm, current episode and historical episode versions remain attached to the run', () => {
 const raw = structuredClone(fixture);
 raw.tasks[0].arms.after_mcp.skill_sha = 'a1980cff'; raw.tasks[0].arms.after_mcp.skill_version = '0.1.0';
 raw.tasks[0].episodes[0].skill_sha = 'a1980cff'; raw.tasks[0].episodes[0].skill_version = '0.1.0';
 raw.tasks[0].labelled_results = { pre_fix: { passed: 0, total: 1, skill_sha: 'pre-a1980cff', skill_version: '0.1.0', episodes: [{ ...raw.tasks[0].episodes[0], skill_sha: 'pre-a1980cff', pass: false }] } };
 const task = normalizeBench(raw).tasks[0];
 assert.equal(task.arms.after_mcp.skillSha, 'a1980cff'); assert.equal(task.arms.after_mcp.skillVersion, '0.1.0');
 assert.equal(task.episodes[0].skillSha, 'a1980cff');
 assert.equal(task.labelledResults[0].result.skillSha, 'pre-a1980cff');
 assert.equal(task.labelledResults[0].episodes[0].skillSha, 'pre-a1980cff');
 assert.match(fmtSkillVersion(task.arms.after_mcp), /0.1.0.*a1980cff/);
 assert.match(fmtSkillVersion(undefined), /not recorded/);
});

test('published ITT failures count in pairing without promoting unrelated void rows', () => {
 const raw = structuredClone(fixture);
 const failure = raw.tasks[0].episodes.find((e) => e.arm === 'after_mcp' && e.seed === 1);
 Object.assign(failure, { valid: true, pass: false, counted_as: 'fail (intention-to-treat): cap after skill failure' });
 const task = normalizeBench(raw).tasks[0];
 const preserved = task.episodes.find((e) => e.arm === 'after_mcp' && e.seed === 1);
 assert.equal(preserved.valid, true); assert.match(preserved.countedAs, /intention-to-treat/); assert.equal(countedEpisode(preserved), true);
 assert.equal(pairedSavings(task).tokenPairs, 5);
 assert.deepEqual(pooledMcNemar([task]), { pairs: 5, forSkill: 0, againstSkill: 1, p: 1 });
 preserved.valid = false;
 assert.equal(countedEpisode(preserved), false); assert.equal(pairedSavings(task).tokenPairs, 4);
});

test('all grouped task IDs pool with unequal denominators; missing or duplicated evidence is refused', () => {
 const dir = mkdtempSync(join(tmpdir(), 'showcase-pool-'));
 try {
  writeFileSync(join(dir, 'showcase.yml'), 'skills: [{ref: ghost/calculator, task_ids: [calc_3plus3, second, third]}]');
  writeFileSync(join(dir, 'skill.yaml'), 'version: 1.0.0\nactions: [{name: calculate}]');
  const bench = normalizeBench(fixture), base = bench.tasks[0];
  bench.tasks.push({ ...base, task_id: 'second', episodes: [0, 1, 2].map((seed) => ({ arm: 'before', seed, valid: true, pass: true })).concat([0, 1].map((seed) => ({ arm: 'after_mcp', seed, valid: true, pass: seed === 0 }))), arms: { before: { passed: 3, total: 3 }, after_mcp: { passed: 1, total: 2 } } });
  bench.tasks.push({ ...base, task_id: 'third', episodes: ['before', 'after_mcp'].map((arm) => ({ arm, seed: 0, valid: true, pass: false })), arms: { before: { passed: 0, total: 1 }, after_mcp: { passed: 0, total: 1 } } });
  const entries = readShowcase({ root: dir, skills: [{ id: 'ghost/calculator', skillDir: dir, benches: [bench] }] });
  assert.equal(entries.length, 1); assert.equal(entries[0].taskIds.length, 3);
  const tasks = listedTasks(entries).map((r) => r.task);
  assert.equal(tasks.length, 3);
  assert.equal(pooledPass(tasks, 'before').total, 9);
  assert.equal(pooledPass(tasks, 'after_mcp').total, 8);
  entries[0].taskIds.push('missing'); assert.throws(() => listedTasks(entries), /expected one bench task/); entries[0].taskIds.pop();
  entries[0].rows.push(entries[0].rows[0]); assert.throws(() => listedTasks(entries), /expected one bench task/); entries[0].rows.pop();
  tasks[1].arms.after_mcp.total = 3; assert.throws(() => listedTasks(entries), /counted episodes disagree/);
  writeFileSync(join(dir, 'showcase.yml'), 'skills: [{ref: ghost/calculator, task_ids: [calc_3plus3, calc_3plus3]}]');
  assert.throws(() => readShowcase({ root: dir, skills: [] }), /Duplicate showcase declaration/);
 } finally { rmSync(dir, { recursive: true, force: true }); }
});

test('exact pooled McNemar uses current paired outcomes across tasks', () => {
 const tasks = Array.from({ length: 6 }, (_, i) => ({ episodes: [
  { arm: 'before', seed: 30, model: 'test', valid: true, pass: i === 5 },
  { arm: 'after_mcp', seed: 30, model: 'test', valid: true, pass: i !== 5 },
 ], labelledResults: [{ episodes: [{ arm: 'after_mcp', valid: true, pass: true }] }] }));
 assert.deepEqual(pooledMcNemar(tasks), { pairs: 6, forSkill: 5, againstSkill: 1, p: .21875 });
});


test('historical ITT labels never promote invalid rows into the current pool', () => {
 const raw = structuredClone(fixture);
 const cap = { ...raw.tasks[0].episodes[0], valid: false, pass: false, counted: true, counting_rule: 'intention-to-treat', invalid_reason: 'token cap' };
 raw.tasks[0].labelled_results = { pre_fix: { passed: 0, total: 1, episodes: [cap] } };
 const task = normalizeBench(raw).tasks[0], historical = task.labelledResults[0].episodes[0];
 assert.match(labelledEpisodeOutcome(historical), /^fail \(intention-to-treat; source marked invalid\)/);
 assert.equal(countedEpisode(historical), false);
 assert.equal(pooledMcNemar([task]).pairs, 5);
 task.episodes.push(historical);
 assert.equal(pooledMcNemar([task]).pairs, 5);
});

test('paired comparison labels use the public arm names', async () => {
 const { pairedLabel, humanBenchText } = await import('../../src/lib/hub/bench.ts');
 assert.equal(pairedLabel('after_mcp_vs_before'), 'Agent + skill vs agent alone');
 assert.equal(pairedLabel('after_replay_vs_before'), 'Skill replay vs agent alone');
 assert.equal(humanBenchText('after_mcp on the pre-fix skill (supply-chain finding)'), 'Agent + skill on the pre-fix skill (supply-chain finding)');
});
