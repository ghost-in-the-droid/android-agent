import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import yaml from 'js-yaml';

export interface ActionPrompts { primary: string; variants: string[] }

/** Read the published skill text, not stale prompts in a generated registry. */
export function readActionPrompts(skillDir: string | null, ref: string, actions: string[]): Record<string, ActionPrompts> {
	if (!skillDir) throw new Error(`${ref}: cannot read required action ref_prompt values without skill.yaml`);
	const raw = yaml.load(readFileSync(join(skillDir, 'skill.yaml'), 'utf8')) as { actions?: { name: string; ref_prompt?: unknown; test_case?: { ref_prompt_variants?: unknown } }[] };
	const result: Record<string, ActionPrompts> = Object.create(null);
	for (const action of raw.actions ?? []) {
		if (typeof action.ref_prompt !== 'string' || !action.ref_prompt.trim()) {
			throw new Error(`${ref}/${action.name}: missing required ref_prompt`);
		}
		const primary = action.ref_prompt.trim();
		const variants = action.test_case?.ref_prompt_variants;
		result[action.name] = { primary, variants: Array.isArray(variants)
			? [...new Set(variants.filter((v): v is string => typeof v === 'string').map((v) => v.trim()).filter((v) => v && v !== primary))].slice(0, 3) : [] };
	}
	for (const action of actions) if (!result[action]) throw new Error(`${ref}/${action}: missing required ref_prompt`);
	return result;
}
