import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import yaml from 'js-yaml';
import { median, countedEpisode, type BenchTask, type BenchArm } from './bench.ts';
import type { Hub } from './registry';

export function readShowcase(hub: Hub) {
	const manifest = yaml.load(readFileSync(join(hub.root, 'showcase.yml'), 'utf8')) as { skills: { ref: string; task_ids?: string[]; task?: string }[] };
	const selected = new Map<string, string[]>();
	for (const { ref, task_ids, task } of manifest.skills) {
		const tasks = selected.get(ref) ?? [];
		for (const id of task_ids ?? (task ? [task] : [])) {
			if (tasks.includes(id)) throw new Error(`Duplicate showcase declaration: ${ref}/${id}`);
			tasks.push(id);
		}
		selected.set(ref, tasks);
	}
	return [...selected].map(([ref, taskIds]) => {
		const entry = { ref, taskIds };
		const skill = hub.skills.find((s) => s.id === entry.ref);
		// The manifest on disk is authoritative for action coverage, even before registry regeneration.
		const spec = skill?.skillDir ? yaml.load(readFileSync(join(skill.skillDir, 'skill.yaml'), 'utf8')) as { version: string; actions: { name: string }[] } : null;
		const actions = spec?.actions.map((a) => a.name) ?? skill?.latestEntry.actions ?? [];
		const rows = skill?.benches.flatMap((bench) => bench.tasks.filter((task) => task.action && actions.includes(task.action)).map((task) => ({ bench, task }))) ?? [];
		return { ...entry, skill, version: spec?.version ?? skill?.latest, actions, rows, covered: new Set(rows.filter(({ task }) => task.arms.before && task.arms.after_mcp).map(({ task }) => task.action)).size };
	});
}

/** Pair current counted episodes by seed within their skill/task, never historical rows. */
export function currentPairs(task: BenchTask) {
	const byArm = new Map<string, Map<number | string, typeof task.episodes[number]>>();
	for (const arm of ['before', 'after_mcp']) {
		const rows = new Map<number | string, typeof task.episodes[number]>();
		for (const e of task.episodes.filter((e) => e.arm === arm && countedEpisode(e))) {
			if (e.seed == null || rows.has(e.seed)) throw new Error(`${task.task_id}/${arm}: missing or duplicate seed ${e.seed}`);
			rows.set(e.seed, e);
		}
		byArm.set(arm, rows);
	}
	return [...byArm.get('before')!.values()].flatMap((before) => {
		const after = byArm.get('after_mcp')!.get(before.seed!);
		return after ? [{ before, after }] : [];
	});
}

function validatePublishedArms(task: BenchTask, ref: string) {
	// Match tools/bench/showcase_pool.py: discrepancies cannot become a partial headline.
	currentPairs(task);
	for (const arm of ['before', 'after_mcp'] as const) {
		const result = task.arms[arm];
		const rows = task.episodes.filter((e) => e.arm === arm && countedEpisode(e));
		if (!result || result.total !== rows.length || result.passed !== rows.filter((e) => e.pass).length) {
			throw new Error(`${ref}/${task.task_id}/${arm}: counted episodes disagree with published arm`);
		}
	}
}

export function pairedSavings(task: BenchTask) {
	const pairs = currentPairs(task);
	const tokens = pairs.filter(({ before: b, after: a }) => b.tokens != null && a.tokens != null);
	const percentages = tokens.filter(({ before: b }) => b.tokens! > 0);
	const actions = pairs.filter(({ before: b, after: a }) => b.uiActions != null && a.uiActions != null);
	return {
		tokens: median(tokens.map(({ before: b, after: a }) => b.tokens! - a.tokens!)), tokenPairs: tokens.length,
		percent: median(percentages.map(({ before: b, after: a }) => 100 * (b.tokens! - a.tokens!) / b.tokens!)), percentPairs: percentages.length,
		actions: median(actions.map(({ before: b, after: a }) => b.uiActions!.total - a.uiActions!.total)), actionPairs: actions.length,
	};
}

export function wilson(passed: number, total: number): [number, number] | null {
	if (total <= 0) return null;
	const z = 1.959963984540054, p = passed / total, denom = 1 + z * z / total;
	const center = (p + z * z / (2 * total)) / denom;
	const half = z * Math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom;
	return [Math.max(0, center - half), Math.min(1, center + half)];
}

export function pooledPass(tasks: BenchTask[], arm: BenchArm) {
	const results = tasks.map((t) => t.arms[arm]).filter((r) => r != null);
	if (!results.length) return null;
	const result = results.reduce((sum, r) => ({ passed: sum.passed + r.passed, total: sum.total + r.total }), { passed: 0, total: 0 });
	return { ...result, ci: wilson(result.passed, result.total) };
}


/** Every declared task must exist exactly once and agree with its current counted episodes. */
export function listedTasks(entries: ReturnType<typeof readShowcase>) {
	return entries.flatMap((entry) => entry.taskIds.flatMap((id) => {
		const matches = entry.rows.filter(({ task }) => task.task_id === id);
		if (matches.length !== 1) throw new Error(`${entry.ref}/${id}: expected one bench task, found ${matches.length}`);
		validatePublishedArms(matches[0].task, entry.ref);
		return [{ ...matches[0], ref: entry.ref }];
	}));
}

export function pooledMcNemar(tasks: BenchTask[]) {
	const pairs = tasks.flatMap(currentPairs);
	if (!pairs.length) return null;
	const forSkill = pairs.filter(({ before, after }) => !before.pass && after.pass).length;
	const againstSkill = pairs.filter(({ before, after }) => before.pass && !after.pass).length;
	const discordant = forSkill + againstSkill;
	let term = 2 ** -discordant, tail = term;
	for (let k = 1; k <= Math.min(forSkill, againstSkill); k++) {
		term *= (discordant - k + 1) / k;
		tail += term;
	}
	return { pairs: pairs.length, forSkill, againstSkill, p: Math.min(1, 2 * tail) };
}

export type ChartMetric = 'tokens' | 'actions' | 'time';
export function metricValue(task: BenchTask, arm: BenchArm, metric: ChartMetric): number | null {
	if (!task.arms[arm]) return null;
	const stats = task.stats.arms[arm];
	if (metric === 'tokens') return stats?.tokensMedian ?? task.arms[arm]?.tokens_median ?? null;
	if (metric === 'actions') return stats?.uiActionsMedian ?? null;
	return stats?.wallMsMedian ?? task.arms[arm]?.wall_ms_median ?? null;
}
export function medianReduction(task: BenchTask, metric: ChartMetric): number | null {
	const before = metricValue(task, 'before', metric), after = metricValue(task, 'after_mcp', metric);
	if (before == null || after == null || before < 0) return null;
	if (before === 0) return after === 0 ? 0 : null;
	return (before - after) / before;
}
