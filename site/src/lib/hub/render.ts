// Untrusted-content rendering for skill READMEs and SOFT.md. Every byte of
// markdown in a skill dir is author-controlled, so raw HTML is parsed and then
// stripped down by rehype-sanitize (GitHub's allowlist). No script, no event
// handlers, no javascript: URLs, images only over https. rehype-raw turns raw
// HTML inside markdown into real nodes first so the sanitizer can inspect them.

import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';
import remarkRehype from 'remark-rehype';
import rehypeRaw from 'rehype-raw';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import rehypeStringify from 'rehype-stringify';
import QRCode from 'qrcode';

const schema = {
	...defaultSchema,
	// Prefix ids so author headings cannot clobber page ids.
	clobberPrefix: 'readme-',
	protocols: { ...defaultSchema.protocols, href: ['http', 'https', 'mailto'], src: ['https'] },
};

export interface DocBase {
	/** Where relative images resolve, e.g. the jsDelivr tag URL of the skill dir. */
	assets: string;
	/** Where relative links resolve, e.g. the GitHub tree URL of the skill dir. */
	links: string;
}

type HNode = { type: string; tagName?: string; properties?: Record<string, unknown>; children?: HNode[] };
const ABSOLUTE = /^(?:[a-z][a-z0-9+.-]*:|\/\/|#)/i;

/** Rewrite relative src/href against the skill's published location so a
 *  README's `demo.gif` loads from jsDelivr instead of 404ing on the site. */
function rehypeRebase(base?: DocBase) {
	return (tree: HNode) => {
		if (!base) return;
		const walk = (n: HNode) => {
			const p = n.properties;
			if (n.type === 'element' && p) {
				for (const [attr, root] of [['src', base.assets], ['href', base.links]] as const) {
					const v = p[attr];
					if (typeof v === 'string' && v && !ABSOLUTE.test(v)) p[attr] = `${root.replace(/\/$/, '')}/${v.replace(/^\.?\//, '')}`;
				}
			}
			n.children?.forEach(walk);
		};
		walk(tree);
	};
}

export async function renderMarkdown(md: string | null, base?: DocBase): Promise<string | null> {
	if (md == null) return null;
	const file = await unified()
		.use(remarkParse)
		.use(remarkGfm)
		.use(remarkRehype, { allowDangerousHtml: true })
		.use(rehypeRaw)
		.use(rehypeSanitize, schema)
		.use(rehypeRebase, base)
		.use(rehypeStringify)
		.process(md);
	return String(file);
}

export async function qrSvg(text: string): Promise<string> {
	return QRCode.toString(text, { type: 'svg', margin: 1, errorCorrectionLevel: 'M', color: { dark: '#050505', light: '#ffffff' } });
}
