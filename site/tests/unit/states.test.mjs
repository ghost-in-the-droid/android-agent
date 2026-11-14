import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { getViteConfig } from 'astro/config';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { stateBadges } from '../../src/lib/hub/states.ts';
let server, component;
before(async () => {
 const config = await getViteConfig({ server: { middlewareMode: true }, logLevel: 'error' })({ command: 'serve', mode: 'test' });
 server = await createServer(config);
 component = (await server.ssrLoadModule('/src/components/hub/SkillActions.astro')).default;
});
after(async () => { await server?.close(); });
test('state labels are declarations, with safe optional data', () => {
 assert.deepEqual(stateBadges(), []);
 assert.deepEqual(stateBadges({ requires_state: ['logged_in'], provides_state: ['app_open'], clears_state: ['logged_in'] }),
  ['Requires: logged in', 'Sets: app open', 'Clears: logged in']);
 assert.deepEqual(stateBadges({ requires_state: ['<script>', 12, 'bad-state'] }), []);
});
test('Hub action renders state badges and beta label', async () => {
 const skill = { id: 'test/auth', latestEntry: { actions: ['read', 'login'], action_states: {
  read: { requires_state: ['logged_in'] }, login: { provides_state: ['logged_in'] } } }, demoClips: [], actionPrompts: { read: { primary: "read", variants: [] }, login: { primary: "login", variants: [] } } };
 const html = await (await AstroContainer.create()).renderToString(component, { props: { skill } });
 assert.match(html, /Requires: logged in/);
 assert.match(html, /Sets: logged in/);
 assert.match(html, /auto-login runner: beta/);
});
test('generated schema validates secret metadata and deterministic state declarations', async () => {
 const { default: validate } = await import('../../src/lib/hub/skill.validate.generated.js');
 const base = { name: 'auth', version: '1.0.0', license: 'MIT', generated_with: 'human',
  state_probes: { logged_in: { kind: 'element_present', text: 'Inbox' } },
  actions: [{ name: 'login', ref_prompt: 'log in', provides_state: ['logged_in'], idempotent: false,
   params: [{ name: 'password', secret: true }], steps: [{ action: 'type_text', text: '{password}' }],
   end_state_validator: { kind: 'element_present', text: 'Inbox' } }] };
 assert.equal(validate(base), true, JSON.stringify(validate.errors));
 for (const edit of [
  (x) => x.actions[0].params[0].default = 'must-not-store',
  (x) => x.actions[0].provides_state = ['logged-in'],
  (x) => x.actions[0].idempotent = 'yes',
  (x) => x.state_probes.logged_in = { kind: 'custom_python', function: 'helpers:probe' },
 ]) {
  const bad = structuredClone(base); edit(bad);
  assert.equal(validate(bad), false);
 }
});
