// Internal link check over dist/ (run after `npm run build`). Exit 1 on any broken internal link.
// External URLs are skipped; localhost example URLs in docs and the platform-injected /_vercel script are not site links.
import { LinkChecker } from 'linkinator';
const checker = new LinkChecker();
const broken = [];
let checked = 0;
checker.on('link', (r) => { checked++; if (r.state === 'BROKEN') broken.push(r); });
await checker.check({
 path: new URL('../dist', import.meta.url).pathname,
 recurse: true,
 linksToSkip: ['^https?://(?!(localhost|127\\.0\\.0\\.1))', '^http://localhost:(?!\\d+/?$)', '^http://localhost:(5055|8002|5173|8000|3000)', '_vercel/insights'],
});
const real = broken.filter((r) => !/localhost:(5055|8002|5173|8000|3000)|_vercel\/insights/.test(r.url) && !/^http:\/\/localhost:\d+\/?$/.test(r.url));
for (const r of real) console.log(`${r.status}\t${r.url}\t<- ${r.parent}`);
console.log(`links checked: ${checked}, internal links broken: ${real.length}`);
process.exit(real.length || checked < 100 ? 1 : 0);
