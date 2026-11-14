// Emits each skill's app icon into dist at build time, straight from the skill
// dir (or the fixture icon until the registry carries `icon`). Nothing is copied
// into site/public and nothing under site/ is committed.
import type { APIRoute, GetStaticPaths } from 'astro';
import { readFileSync } from 'node:fs';
import { loadHub } from '../../../../lib/hub/registry';

export const getStaticPaths: GetStaticPaths = () =>
	loadHub().skills.filter((s) => s.iconFile).map((s) => ({ params: { author: s.author, slug: s.slug }, props: { file: s.iconFile } }));

export const GET: APIRoute = ({ props }) =>
	new Response(readFileSync(props.file as string), { headers: { 'Content-Type': 'image/webp' } });
