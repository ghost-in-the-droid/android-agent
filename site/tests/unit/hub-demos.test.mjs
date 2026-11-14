// loadHub() end to end on a tiny hub dir: recorded session clips (demo.webm, demos/<action>.webm) and the
// before / after pair (demos/before-after.webm + .json) resolve into tabs and routes; the clean catalog still wins.
// Runs in its own process (node --test spawns one per file), so HUB_DIR is set before the loader is imported;
// the loader comes through Vite because its relative imports carry no extension.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'vite';
import { getViteConfig } from 'astro/config';

let server;

const root = mkdtempSync(join(tmpdir(), 'hub-demos-'));
const skillYaml = (actions) => ['name: x', 'version: 1.0.0', 'actions:', ...actions.map((a) => `  - name: ${a}\n    ref_prompt: do ${a}`)].join('\n') + '\n';
const version = (actions) => ({ tag: null, commit: 'abc', fingerprint: { os: 'android', app_package: 'org.example' }, actions, data_access: [], has_python: false, files: { 'skill.yaml': 'sha256:0' }, size_bytes: 10 });
const quality = { tier: 'draft', points: 0, signals: { readme: false, soft_md: false, demo: true, bench: false, tests_pass: null, fingerprints_verified: 0, last_verified: null } };
const metrics = { schema_version: 1, action: 'go', prompt: 'go now', ok_means: 'verified_task_check', before: { seconds: 40, tokens: 400000, tool_calls: 12, ok: true }, after: { seconds: 10, tokens: 20000, tool_calls: 3, ok: true }, notes: 'n' };
const skill = (slug, actions, extra) => ({ author: 'alice', slug, name: slug, description: `${slug} skill`, skill_class: 'hard', trust: 'unverified', latest: '1.0.0', versions: { '1.0.0': version(actions) }, quality, updated_at: '2026-11-03T00:00:00Z', icon: null, demo: null, demos: {}, before_after: null, ...extra });

before(() => {
	// recorded: skill-level demo.webm + pair with numbers
	const rec = join(root, 'alice', 'recorded'); mkdirSync(join(rec, 'demos'), { recursive: true });
	writeFileSync(join(rec, 'skill.yaml'), skillYaml(['go', 'stop']));
	writeFileSync(join(rec, 'demo.webm'), 'clip'); writeFileSync(join(rec, 'demos', 'before-after.webm'), 'pair');
	// actiononly: demos/go.webm is also the registry default clip (no separate overview tab); pair without numbers
	const act = join(root, 'alice', 'actiononly'); mkdirSync(join(act, 'demos'), { recursive: true });
	writeFileSync(join(act, 'skill.yaml'), skillYaml(['go', 'stop']));
	writeFileSync(join(act, 'demos', 'go.webm'), 'go clip'); writeFileSync(join(act, 'demos', 'before-after.mp4'), 'pair');
	// both: an action clip is the registry default AND demo.webm exists on disk -> overview tab from demo.webm
	const both = join(root, 'alice', 'both'); mkdirSync(join(both, 'demos'), { recursive: true });
	writeFileSync(join(both, 'skill.yaml'), skillYaml(['go']));
	writeFileSync(join(both, 'demos', 'go.webm'), 'go clip'); writeFileSync(join(both, 'demo.webm'), 'overview');
	// broken: pair file missing on disk, numbers malformed
	const bad = join(root, 'alice', 'broken'); mkdirSync(bad, { recursive: true });
	writeFileSync(join(bad, 'skill.yaml'), skillYaml(['go']));
	writeFileSync(join(root, 'registry.json'), JSON.stringify({
		schema_version: 2, generated_at: '2026-11-03T00:00:00Z', repo: 'o/r', authors: { alice: { trust: 'unverified', github: 'alice', skills: 4 } },
		skills: {
			'alice/recorded': skill('recorded', ['go', 'stop'], { demo: { path: 'demo.webm', type: 'video/webm' }, before_after: { clip: { path: 'demos/before-after.webm', type: 'video/webm' }, metrics } }),
			'alice/actiononly': skill('actiononly', ['go', 'stop'], { demo: { path: 'demos/go.webm', type: 'video/webm' }, demos: { go: { path: 'demos/go.webm', type: 'video/webm' } }, before_after: { clip: { path: 'demos/before-after.mp4', type: 'video/mp4' }, metrics: null } }),
			'alice/broken': skill('broken', ['go'], { before_after: { clip: { path: 'demos/before-after.webm' }, metrics: { schema_version: 1 } } }),
			'alice/both': skill('both', ['go'], { demo: { path: 'demos/go.webm', type: 'video/webm' }, demos: { go: { path: 'demos/go.webm', type: 'video/webm' } } }),
		},
	}));
	process.env.HUB_DIR = root;
});
after(async () => { await server?.close(); rmSync(root, { recursive: true, force: true }); });

test('recorded clips and the pair resolve into tabs, routes and the list badge', async () => {
	const config = await getViteConfig({ server: { middlewareMode: true }, logLevel: 'error' })({ command: 'serve', mode: 'test' });
	server = await createServer(config);
	const { loadHub } = await server.ssrLoadModule('/src/lib/hub/registry.ts');
	const hub = loadHub();
	const by = Object.fromEntries(hub.skills.map((s) => [s.id, s]));
	const rec = by['alice/recorded'];
	assert.deepEqual(rec.demoClips.map((c) => [c.label, c.clean, c.url]), [['Overview', false, '/skills/demos/alice/recorded.webm']]);
	assert.deepEqual(rec.demoMissing, ['go', 'stop']);
	assert.equal(rec.beforeAfter.url, '/skills/demos/alice/recorded/before-after.webm');
	assert.equal(rec.beforeAfter.kind, 'webm');
	assert.equal(rec.beforeAfter.summary.headline, '20× fewer tokens, 4× faster');
	assert.equal(rec.beforeAfter.metrics.prompt, 'go now');

	const act = by['alice/actiononly'];
	assert.deepEqual(act.demoClips.map((c) => [c.action, c.clean, c.url]), [['go', false, '/skills/demos/alice/actiononly/go.webm']]);
	assert.equal(act.demo, null, 'the action clip is not duplicated as an overview tab');
	assert.deepEqual(act.demoMissing, ['stop']);
	assert.equal(act.beforeAfter.kind, 'mp4');
	assert.equal(act.beforeAfter.metrics, null);
	assert.equal(act.beforeAfter.summary, null);

	const both = by['alice/both'];
	assert.deepEqual(both.demoClips.map((c) => [c.label, c.clean, c.url]), [['Overview', false, '/skills/demos/alice/both.webm'], ['go', false, '/skills/demos/alice/both/go.webm']]);
	assert.ok(both.demo && both.demo.file.endsWith('/demo.webm'));

	const bad = by['alice/broken'];
	assert.equal(bad.beforeAfter, null, 'a pair clip missing on disk is skipped');
	assert.ok(hub.warnings.some((w) => /alice\/broken: before\/after clip demos\/before-after.webm not found/.test(w)), hub.warnings.join('\n'));
});
