// Emits each skill's demo clip into dist at build time, straight from the skill
// dir (validated against the clean-demo catalog). Nothing is copied
// into site/public and nothing under site/ is committed.
import type { APIRoute, GetStaticPaths } from 'astro';
import { readFileSync } from 'node:fs';
import { DEMO_MIME, loadHub, type DemoKind } from '../../../../lib/hub/registry';

export const getStaticPaths: GetStaticPaths = () =>
	loadHub().skills.filter((s) => s.demo).map((s) => ({
		params: { author: s.author, file: `${s.slug}.${s.demo!.kind}` },
		props: { file: s.demo!.file, kind: s.demo!.kind },
	}));

export const GET: APIRoute = ({ props }) =>
	new Response(readFileSync(props.file as string), { headers: { 'Content-Type': DEMO_MIME[props.kind as DemoKind] } });
