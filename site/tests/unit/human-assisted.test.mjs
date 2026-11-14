import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { getViteConfig } from 'astro/config';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
let server, component, lookup;
before(async () => {
 const config = await getViteConfig({ server: { middlewareMode: true }, logLevel: 'error' })({ command: 'serve', mode: 'test' });
 server = await createServer(config);
 component = (await server.ssrLoadModule('/src/components/hub/HumanAssistedDemo.astro')).default;
 lookup = (await server.ssrLoadModule('/src/lib/hub/human-assisted.ts')).humanAssistedDemoFor;
});
after(async () => { await server?.close(); });
test('human-assisted video is clearly unscored, accessible and fetched only on demand', async () => {
 const demo = { url: '/media/human-assisted/signup.mp4', captions: '/media/human-assisted/signup.vtt', poster: '/media/human-assisted/signup-poster.webp', date: '2026-10-24', device: 'Samsung Galaxy A03s' };
 const html = await (await AstroContainer.create()).renderToString(component, { props: { demo } });
 assert.match(html, /data-scored="false"/);
 assert.match(html, /human-assisted captcha demo, not a replay/);
 assert.match(html, /adds no scored run, replay success, device coverage, or score points/);
 assert.match(html, /type="video\/mp4"/);
 assert.match(html, /original speed and resolution/);
 assert.match(html, /preload="none"/);
 assert.match(html, /kind="captions"/);
 assert.doesNotMatch(html, /autoplay|data-demo-link|demo-a-register/);
});
test('editorial video lookup never attaches media to an unrelated skill', () => {
 assert.equal(lookup('ghost/calculator'), undefined);
 assert.equal(lookup('unknown/signup'), undefined);
});
