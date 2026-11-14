import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createServer } from 'vite';
import { getViteConfig } from 'astro/config';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
let server, component, rep;
before(async () => {
 const config = await getViteConfig({ server: { middlewareMode: true }, logLevel: 'error' })({ command: 'serve', mode: 'test' });
 server = await createServer(config);
 component = (await server.ssrLoadModule('/src/components/hub/RepSummary.astro')).default;
 rep = await server.ssrLoadModule('/src/lib/hub/rep.ts');
});
after(async () => { await server?.close(); });
const table = JSON.parse(readFileSync(new URL('../../../skillhub/scoring/rep-v1.json', import.meta.url), 'utf8'));
const person = (login, rep_, b, badges = []) => ({ login, github: login, trust: null, maintainers: [], rep: rep_, breakdown: b, published: [], verified: [], maintained: [], stats: {}, badges });
const render = async (props) => (await (await AstroContainer.create()).renderToString(component, { props: { table, ...props } })).replace(/ data-astro-source-[a-z]+="[^"]*"/g, '');

test('rep summary shows the total, the three parts and badge labels from rep-v1.json', async () => {
 const html = await render({ contributor: person('carol', 31, { published: 0, verified: 29, maintained: 2 }, ['verifier', 'device_pioneer']) });
 assert.match(html, /data-rep="31"/);
 assert.match(html, /<strong>31<\/strong> rep/);
 assert.match(html, /data-rep-part="verified"[^>]*><strong>29<\/strong>verified/);
 assert.match(html, /data-badge="device_pioneer"[^>]*>Device pioneer</);
 assert.doesNotMatch(html, /data-badge="author"/);
});
test('no contributor means an honest empty state, never a zero score', async () => {
 const html = await render({ contributor: null, note: 'Imported benchmark scaffolds have no human author and earn no rep.' });
 assert.match(html, /data-rep="none"/);
 assert.match(html, /earn no rep/);
 assert.doesNotMatch(html, /<strong>0<\/strong> rep/);
});
test('ranking is by rep, then verified, then login; avatars only for GitHub logins', () => {
 const list = [person('b', 10, { published: 10, verified: 0, maintained: 0 }), person('a', 10, { published: 0, verified: 10, maintained: 0 }), person('c', 50, { published: 50, verified: 0, maintained: 0 })];
 assert.deepEqual(rep.rankContributors(list).map((c) => c.login), ['c', 'a', 'b']);
 assert.equal(rep.avatarUrl('C-K-Loan'), 'https://github.com/C-K-Loan.png?size=128');
 for (const bad of ['', '-x', 'a--b', 'x/y', '../x', 'a'.repeat(40)]) assert.equal(rep.avatarUrl(bad), null, bad);
});
test('scoring-page point rules are generated from the table values', () => {
 const rows = rep.repPointRules(table);
 assert.ok(rows.some((r) => r.points === `${table.verified.independent_run} per counted run`));
 assert.ok(rows.some((r) => r.points === `${table.maintained.per_skill} per skill`));
 assert.ok(rows.some((r) => /Downloads/.test(r.source) && r.points === '0'));
});
