import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createServer } from 'vite';
import { getViteConfig } from 'astro/config';

let server, loadHub, pickExample, workedExample;
before(async () => {
	const config = await getViteConfig({ server: { middlewareMode: true }, logLevel: 'error' })({ command: 'serve', mode: 'test' });
	server = await createServer(config);
	({ loadHub } = await server.ssrLoadModule('/src/lib/hub/registry.ts'));
	({ pickExample, workedExample } = await server.ssrLoadModule('/src/lib/hub/worked-example.ts'));
});
after(async () => { await server?.close(); });

const raw = JSON.parse(readFileSync(new URL('../../../skillhub/registry.json', import.meta.url), 'utf8'));

test('the scoring page example is recomputed from skillhub/registry.json, not typed', () => {
	const [id, entry] = Object.entries(raw.skills).sort(([ai, a], [bi, b]) => b.quality.points - a.quality.points || ai.localeCompare(bi))[0];
	const skill = pickExample(loadHub().skills);
	assert.equal(skill.id, id);
	const ex = workedExample(skill);
	const q = entry.quality;
	assert.deepEqual(Object.fromEntries(ex.rows.map((r) => [r.id, r.points])), {
		docs: q.categories.docs, self_evidence: q.categories.self_evidence, independent: q.categories.independent,
		community_usage: q.categories.community_usage ?? q.categories.usage ?? 0, maintenance: q.categories.maintenance,
	});
	assert.equal(ex.subtotal, Object.values(q.categories).reduce((n, v) => n + v, 0));
	assert.equal(ex.freshness, q.freshness_multiplier);
	assert.equal(Math.round(ex.subtotal * ex.freshness), q.score);
	assert.equal(ex.score, q.score);
	assert.equal(ex.evidence.self.total, q.runs.self.total);
	assert.equal(ex.evidence.independent.total, q.runs.independent.total);
	assert.equal(ex.cells, q.runs.device_grid.cells.length);
	assert.ok(ex.rows.every((r) => r.points <= r.cap));
});
