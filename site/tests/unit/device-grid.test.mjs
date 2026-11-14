import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { getViteConfig } from 'astro/config';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
let server, component;
before(async () => {
 const config = await getViteConfig({ server: { middlewareMode: true }, logLevel: 'error' })({ command: 'serve', mode: 'test' });
 server = await createServer(config);
 component = (await server.ssrLoadModule('/src/components/hub/DeviceCoverage.astro')).default;
});
after(async () => { await server?.close(); });
const cell = { app_version: '1.0', os_version: '14', screen: '1080x2400', density: '420', locale: 'en-US', independent: 0, maintainer: 0 };
const render = async (cells) => (await AstroContainer.create()).renderToString(component, { props: { grid: { cells, independent_cells: cells.filter((c) => c.independent > 0 && c.locale !== '*').length } } });
test('device coverage renders covered and recorded cells separately, including shared cells', async () => {
 const html = await render([{ ...cell, independent: 2, maintainer: 3 }, { ...cell, locale: 'de-DE', maintainer: 1 }]);
 assert.match(html, /1 independent cell/);
 assert.equal((html.match(/data-device-covered/g) ?? []).length, 1);
 assert.equal((html.match(/data-device-recorded/g) ?? []).length, 2);
 assert.match(html, /2 independent/);
 assert.match(html, /3 maintainer runs<span class="unrec note[^"]*"[^>]*>not independent/);
 assert.match(html, /1080x2400 @ 420 dpi/);
 assert.match(html, /en-US/);
});
test('device coverage has the honest empty state and incomplete records never appear covered', async () => {
 for (const cells of [[], [{ ...cell, maintainer: 1 }], [{ ...cell, locale: '*', independent: 1 }]]) {
  const html = await render(cells);
  assert.match(html, /No independent device runs yet\./);
  assert.match(html, /0 independent cells/);
  assert.doesNotMatch(html, /data-device-covered/);
 }
 assert.match(await render([{ ...cell, locale: '*', independent: 1 }]), /independent, incomplete/);
});
test('friendly labels accompany measurements without granting independent coverage', async () => {
 const html = await render([{ ...cell, maintainer: 4, device_labels: ['Samsung Galaxy A03s'] }]);
 assert.match(html, /Samsung Galaxy A03s<\/dd>/);
 assert.match(html, /4 maintainer/);
 assert.match(html, /0 independent cells/);
 assert.doesNotMatch(html, /data-device-covered/);
});
