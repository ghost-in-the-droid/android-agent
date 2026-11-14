// The scoring page's worked example: one real registry entry, every number read from it (never typed).
import { CATEGORIES, TIERS, MAX_POINTS, MAINTENANCE_DECAY_DAYS, categoryPoints } from './scoring';
import type { Skill } from './registry';

/** Highest-scoring skill in the registry; ties break on id so the pick is stable between builds. */
export function pickExample(skills: Skill[]): Skill | undefined {
	return [...skills].sort((a, b) => b.quality.points - a.quality.points || a.id.localeCompare(b.id))[0];
}

export function workedExample(skill: Skill) {
	const q = skill.quality;
	const runs = (q.runs ?? {}) as Record<string, any>;
	const rows = CATEGORIES.map((c) => ({ id: c.id, label: c.label, cap: c.cap, points: categoryPoints(q.categories, c.id) }));
	const subtotal = rows.reduce((n, r) => n + Math.min(r.points, r.cap), 0);
	const freshness = q.freshness_multiplier ?? 1;
	const tierIdx = TIERS.findIndex((t) => t.id === q.tier);
	const next = TIERS[tierIdx + 1];
	const cls = (k: string) => ({ passed: runs[k]?.passed ?? 0, total: runs[k]?.total ?? 0 });
	return {
		id: skill.id,
		trust: skill.trust,
		tier: q.tier,
		next: next ? { label: next.label, points: next.points, missing: Math.max(0, next.points - q.points) } : null,
		rows,
		subtotal,
		freshness,
		score: q.score,
		points: q.points,
		max: MAX_POINTS,
		evidence: { self: cls('self'), maintainer: cls('maintainer'), independent: cls('independent') },
		cells: (runs.device_grid?.cells ?? []).length,
		independentCells: runs.device_grid?.independent_cells ?? 0,
		decayDays: MAINTENANCE_DECAY_DAYS,
	};
}
