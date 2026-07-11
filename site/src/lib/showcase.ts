/**
 * Build-time loader for showcase demo specs.
 * Reads site/public/showcase/<demo>/spec.yaml (written by scripts/record_demo.py
 * or the placeholder generator). Runs only at build — ships zero client JS.
 */
import fs from 'node:fs';
import path from 'node:path';
import { load as yamlLoad } from 'js-yaml';

export interface DemoSpec {
	demo: string;
	title: string;
	category: 'ai-integration' | 'llm-providers' | 'platform' | 'dev-tools';
	featured?: boolean;
	placeholder?: boolean;
	docs?: string;
	outro?: { cta_line?: string; cta_link?: string };
	[key: string]: unknown;
}

const SHOWCASE_DIR = path.resolve('public/showcase');

export const CATEGORY_LABELS: Record<string, string> = {
	'ai-integration': 'AI Integration',
	'llm-providers': 'LLM Providers',
	platform: 'Platform',
	'dev-tools': 'Dev Tools',
};

export function loadSpec(slug: string): DemoSpec | null {
	const file = path.join(SHOWCASE_DIR, slug, 'spec.yaml');
	if (!fs.existsSync(file)) return null;
	return yamlLoad(fs.readFileSync(file, 'utf8')) as DemoSpec;
}

export function loadAllSpecs(): DemoSpec[] {
	if (!fs.existsSync(SHOWCASE_DIR)) return [];
	return fs
		.readdirSync(SHOWCASE_DIR, { withFileTypes: true })
		.filter((e) => e.isDirectory() && !e.name.startsWith('_'))
		.map((e) => loadSpec(e.name))
		.filter((s): s is DemoSpec => s !== null)
		.sort((a, b) => a.title.localeCompare(b.title));
}

export function loadSnippet(slug: string): string {
	const file = path.join(SHOWCASE_DIR, slug, 'snippet.py');
	return fs.existsSync(file) ? fs.readFileSync(file, 'utf8').trimEnd() : '';
}

/** Asset URLs (files under public/ are served from the site root). */
export function demoAssets(slug: string) {
	return {
		poster: `/showcase/${slug}/poster.png`,
		video: `/showcase/${slug}/demo.webm`,
	};
}

/** Marketing copy (hooks/captions/CTAs) keyed by demo id — from copy.yaml. */
export function loadCopy(): Record<string, { title: string; hook?: string; sizzle_order?: number }> {
	const file = path.join(SHOWCASE_DIR, 'copy.yaml');
	if (!fs.existsSync(file)) return {};
	const data = yamlLoad(fs.readFileSync(file, 'utf8')) as {
		demos: { id: string; title: string; hook?: string; sizzle_order?: number }[];
	};
	return Object.fromEntries(data.demos.map((d) => [d.id, d]));
}
