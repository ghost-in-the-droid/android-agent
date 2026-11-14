// Emits per-action demo clips and the before / after pair into dist at build time:
// /skills/demos/<author>/<slug>/<action>.<ext> and /skills/demos/<author>/<slug>/before-after.<ext>,
// straight from the skill dir (clean-catalog clips, recorded session clips and the pair clip, each
// validated by the registry loader). Never site/public.
import type { APIRoute, GetStaticPaths } from 'astro';
import { readFileSync } from 'node:fs';
import { BEFORE_AFTER_STEM, DEMO_MIME, loadHub, type DemoKind } from '../../../../../lib/hub/registry';

export const getStaticPaths: GetStaticPaths = () =>
	loadHub().skills.flatMap((s) => [
		...s.demoClips.filter((c) => c.action).map((c) => ({
			params: { author: s.author, slug: s.slug, file: `${c.action}.${c.kind}` },
			props: { file: c.file, kind: c.kind },
		})),
		...(s.beforeAfter ? [{
			params: { author: s.author, slug: s.slug, file: `${BEFORE_AFTER_STEM}.${s.beforeAfter.kind}` },
			props: { file: s.beforeAfter.file, kind: s.beforeAfter.kind },
		}] : []),
	]);

export const GET: APIRoute = ({ props }) =>
	new Response(readFileSync(props.file as string), { headers: { 'Content-Type': DEMO_MIME[props.kind as DemoKind] } });
