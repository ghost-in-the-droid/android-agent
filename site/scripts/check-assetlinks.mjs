// Postbuild check: dist/.well-known/assetlinks.json exists, is valid JSON and
// has the Digital Asset Links shape. Placeholder values only warn, so the
// site still builds before the maintainer fills in the release certificate.
import { readFileSync } from 'node:fs';

const path = new URL('../dist/.well-known/assetlinks.json', import.meta.url);
const fail = (msg) => { console.error(`assetlinks check FAILED: ${msg}`); process.exit(1); };
let doc;
try { doc = JSON.parse(readFileSync(path, 'utf8')); } catch (e) { fail(`${path.pathname}: ${e.message}`); }
if (!Array.isArray(doc) || doc.length === 0) fail('top level must be a non-empty array');
const SHA = /^([0-9A-F]{2}:){31}[0-9A-F]{2}$/;
let placeholder = false;
for (const st of doc) {
	if (!st.relation?.includes('delegate_permission/common.handle_all_urls')) fail('missing handle_all_urls relation');
	const t = st.target ?? {};
	if (t.namespace !== 'android_app') fail('target.namespace must be android_app');
	if (typeof t.package_name !== 'string' || !t.package_name) fail('target.package_name missing');
	if (!Array.isArray(t.sha256_cert_fingerprints) || !t.sha256_cert_fingerprints.length) fail('sha256_cert_fingerprints missing');
	for (const f of [t.package_name, ...t.sha256_cert_fingerprints]) if (f.startsWith('PLACEHOLDER')) placeholder = true;
	for (const f of t.sha256_cert_fingerprints) if (!f.startsWith('PLACEHOLDER') && !SHA.test(f)) fail(`bad fingerprint ${f} (want 32 uppercase hex pairs joined by colons)`);
	if (!t.package_name.startsWith('PLACEHOLDER') && !/^[a-zA-Z][\w]*(\.[a-zA-Z][\w]*)+$/.test(t.package_name)) fail(`bad package name ${t.package_name}`);
}
console.log(`assetlinks.json OK${placeholder ? ' (PLACEHOLDER values: see docs/app-links.md)' : ''}`);
