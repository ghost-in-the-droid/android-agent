// Page-weight budget for the Skill Hub, run after `astro build`.
// Gate: every /skills/ hub page's initial load (HTML plus the same-origin CSS,
// JS and eager images it references) must stay under 320 KB (warn above 280 KB). Lazy-loaded app
// icons are reported separately (demo clips, preload="none", are never counted) as "all icons": over budget there is a warning,
// not a failure, because a visitor only fetches the icons scrolled into view.
// Third-party fonts and the CDN Monaco editor are excluded.
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const DIST = new URL('../dist/', import.meta.url).pathname;
const BUDGET = 320 * 1024; // raised from 200 KB for the ~114-skill catalogue (~1.8 KB per listed skill)
const WARN = 280 * 1024;
const DOCS = new Set(['overview', 'using-skills', 'creating-skills', 'skill-creation-guide', 'elements', 'publishing', 'contribute']);

function* pages(dir) {
	for (const name of readdirSync(dir)) {
		const p = join(dir, name);
		if (statSync(p).isDirectory()) {
			if (dir.endsWith('/skills') && DOCS.has(name)) continue; // Starlight docs pages
			yield* pages(p);
		} else if (name.endsWith('.html')) yield p;
	}
}

const size = (url) => { const f = join(DIST, url); return existsSync(f) ? statSync(f).size : 0; };
const kb = (n) => `${(n / 1024).toFixed(1)} KB`;
let failed = 0, n = 0;
const worst = { initial: [0, ''], all: [0, ''] };
for (const page of pages(join(DIST, 'skills'))) {
	const html = readFileSync(page, 'utf8');
	const rel = page.slice(DIST.length);
	const assets = new Set([...html.matchAll(/(?:href|src)="(\/_astro\/[^"]+)"/g)].map((m) => m[1]));
	const eager = new Set(), lazy = new Set();
	// Video posters are fetched up front; demo clips themselves (preload="none") are not counted.
	for (const m of html.matchAll(/\bposter="(\/[^"]+)"/g)) eager.add(m[1]);
	for (const m of html.matchAll(/<img\b[^>]*>/g)) {
		const src = /\bsrc="(\/[^"]+)"/.exec(m[0])?.[1];
		if (src) (/\bloading="lazy"/.test(m[0]) ? lazy : eager).add(src);
	}
	let initial = Buffer.byteLength(html);
	for (const a of [...assets, ...eager]) initial += size(a);
	let all = initial;
	for (const a of lazy) if (!eager.has(a)) all += size(a);
	n++;
	if (initial > worst.initial[0]) worst.initial = [initial, rel];
	if (all > worst.all[0]) worst.all = [all, rel];
	if (initial > BUDGET) { failed++; console.error(`OVER BUDGET ${kb(initial)}  ${rel}`); }
	else if (initial > WARN) console.warn(`warn: ${rel} is ${kb(initial)} initial, above the ${WARN / 1024} KB warning line`);
	else if (all > BUDGET) console.warn(`warn: ${rel} is ${kb(initial)} initial but ${kb(all)} if every lazy icon loads`);
}
console.log(`hub pages: ${n}, heaviest initial ${kb(worst.initial[0])} (${worst.initial[1]}), heaviest with all icons ${kb(worst.all[0])} (${worst.all[1]}), budget ${BUDGET / 1024} KB (warn ${WARN / 1024} KB)`);
process.exit(failed ? 1 : 0);
