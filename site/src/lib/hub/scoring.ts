// Public scoring formula. Categories, caps and tier thresholds come from ONE
// file, `skillhub/scoring/v1.json` (owned by the registry builder), read at
// build time. The site carries no point values of its own: this module only
// adds human labels and the hard-gate prose. Until the real file exists the
// build uses `tools/fixtures/scoring-v1.json` (same shape). The build fails if
// the caps do not sum to 100 or the thresholds are not a valid ladder.

import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

export type Tier = 'draft' | 'runs' | 'proven' | 'hardened' | 'reference';
export type Trust = 'official' | 'verified' | 'benchmark' | 'unverified' | 'quarantined';

export const TIER_IDS: Tier[] = ['draft', 'runs', 'proven', 'hardened', 'reference'];
export const MAX_POINTS = 100;

export interface ScoringConfig {
	version: string;
	source: 'live' | 'fixture';
	path: string;
	/** Ordered as in the file. `items` holds per-source points when the file lists them;
	 *  structured items (v1.1 `validators`, `self_reliability`) are flattened to a readable rule. */
	categories: { id: string; cap: number; items: [string, number][]; rules: [string, string][] }[];
	/** v1.1 self-reliability signal, or null on a v1 file. */
	selfReliability: { cap: number; minRuns: number } | null;
	/** v1.1 per-action validator weights, or null on a v1 file. */
	validatorRule: { each: number; cap: number; per: string; weights: Record<string, number> } | null;
	thresholds: Record<Tier, number>;
	raw: Record<string, unknown>;
}

const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined);

/** Accepts `categories` or `caps` as {id: n}, {id: {cap, ...}} or [{id, cap}], and
 *  `tiers` or `thresholds` as {tier: n}, {tier: {points|min_points|threshold}} or
 *  [{id|tier, points|...}]. The contract fixes the numbers, not the nesting. */
export function normalizeScoring(raw: Record<string, any>, source: 'live' | 'fixture', path: string): ScoringConfig {
	const catSrc = raw.categories ?? raw.caps;
	const categories: ScoringConfig['categories'] = [];
	let selfReliability: ScoringConfig['selfReliability'] = null;
	let validatorRule: ScoringConfig['validatorRule'] = null;
	const pushCat = (id: string, v: any) => {
		const cap = num(v) ?? num(v?.cap) ?? num(v?.max) ?? num(v?.points);
		if (cap === undefined) throw new Error(`scoring: category ${id} has no numeric cap`);
		const items: [string, number][] = [];
		const rules: [string, string][] = [];
		const itemSrc = v && typeof v === 'object' ? (v.items ?? v.sources ?? v) : {};
		for (const [k, iv] of Object.entries(itemSrc)) {
			if (['cap', 'max', 'points', 'label', 'description'].includes(k)) continue;
			if (num(iv) !== undefined) { items.push([k, iv as number]); continue; }
			if (!iv || typeof iv !== 'object') continue;
			const o = iv as Record<string, any>;
			const each = num(o.each), icap = num(o.cap), minRuns = num(o.min_runs);
			if (each !== undefined && icap !== undefined) {
				const per = typeof o.per === 'string' ? ` per ${o.per}` : '';
				const weights = o.weights && typeof o.weights === 'object' ? Object.entries(o.weights).filter(([, w]) => num(w) !== undefined) as [string, number][] : [];
				rules.push([k, `+${each} each${per}, up to +${icap}${weights.length ? ` (weights: ${weights.map(([wk, w]) => `${wk.replace(/_/g, ' ')} x${w}`).join(', ')})` : ''}`]);
				if (k === 'validators') validatorRule = { each, cap: icap, per: typeof o.per === 'string' ? o.per : 'skill', weights: Object.fromEntries(weights) };
			} else if (icap !== undefined && minRuns !== undefined) {
				rules.push([k, `up to +${icap}, Wilson lower bound over your own verified runs once ${minRuns} exist${o.per === 'action' ? ' on every action' : ''}`]);
				if (k === 'self_reliability') selfReliability = { cap: icap, minRuns };
			} else if (icap !== undefined) {
				rules.push([k, `up to +${icap}`]);
			}
		}
		categories.push({ id, cap, items, rules });
	};
	if (Array.isArray(catSrc)) catSrc.forEach((c: any) => pushCat(String(c.id ?? c.name), c));
	else if (catSrc && typeof catSrc === 'object') for (const [id, v] of Object.entries(catSrc)) pushCat(id, v);
	else throw new Error(`scoring: ${path} has no categories`);

	const tierSrc = raw.tiers ?? raw.thresholds ?? raw.tier_thresholds;
	const thresholds = {} as Record<Tier, number>;
	const pts = (v: any) => num(v) ?? num(v?.points) ?? num(v?.min_points) ?? num(v?.threshold);
	if (Array.isArray(tierSrc)) tierSrc.forEach((t: any) => { thresholds[String(t.id ?? t.tier ?? t.name).toLowerCase() as Tier] = pts(t) as number; });
	else if (tierSrc && typeof tierSrc === 'object') for (const [id, v] of Object.entries(tierSrc)) thresholds[id.toLowerCase() as Tier] = pts(v) as number;
	return { version: String(raw.version ?? raw.scoring_version ?? 'v1'), source, path, categories, thresholds, raw, selfReliability, validatorRule };
}

/** Build-time contract: caps sum to MAX_POINTS, thresholds form an ascending ladder in [0, MAX_POINTS]. */
export function assertScoring(cfg: ScoringConfig): void {
	const sum = cfg.categories.reduce((n, c) => n + c.cap, 0);
	if (sum !== MAX_POINTS) {
		throw new Error(`scoring: category caps in ${cfg.path} sum to ${sum}, must be ${MAX_POINTS} (${cfg.categories.map((c) => `${c.id}=${c.cap}`).join(', ')})`);
	}
	const declaredMax = num(cfg.raw.max_points);
	if (declaredMax !== undefined && declaredMax !== MAX_POINTS) throw new Error(`scoring: max_points is ${declaredMax}, must be ${MAX_POINTS}`);
	let prev = -1;
	for (const t of TIER_IDS) {
		const v = cfg.thresholds[t];
		if (v === undefined) throw new Error(`scoring: tier threshold for ${t} missing in ${cfg.path}`);
		if (v < 0 || v > MAX_POINTS || v <= prev) throw new Error(`scoring: tier thresholds must rise from 0 to at most ${MAX_POINTS}; ${t}=${v} after ${prev}`);
		prev = v;
	}
	if (cfg.thresholds.draft !== 0) throw new Error(`scoring: draft threshold must be 0, got ${cfg.thresholds.draft}`);
}

function locateScoring(): { path: string; source: 'live' | 'fixture' } {
	const repo = resolve(process.cwd(), '..');
	const hub = process.env.HUB_DIR ? resolve(process.env.HUB_DIR) : join(repo, 'skillhub');
	const live = join(hub, 'scoring', 'v1.json');
	if (existsSync(live)) return { path: live, source: 'live' };
	return { path: join(repo, 'tools', 'fixtures', 'scoring-v1.json'), source: 'fixture' };
}

export function loadScoring(): ScoringConfig {
	const { path, source } = locateScoring();
	const cfg = normalizeScoring(JSON.parse(readFileSync(path, 'utf8')), source, path);
	assertScoring(cfg);
	if (source === 'fixture') console.warn(`[skillhub] scoring: skillhub/scoring/v1.json not found, using ${path}`);
	return cfg;
}

export const SCORING = loadScoring();
export const SCORING_VERSION = SCORING.version;

// ── Prose only below: labels and hard gates. No point values. ──

const TIER_COPY: Record<Tier, { label: string; gates: string[] }> = {
	draft: { label: 'Draft', gates: ['skill.yaml validates', 'Static scan is clean'] },
	runs: { label: 'Runs', gates: ['README present', 'One signed self-run artifact (fingerprint hash, app version, per-step result)'] },
	proven: { label: 'Proven', gates: [
		'Your own signed passing run of the current version on every action',
		'A demo clip of 3 MB or less (webm, mp4 or gif)',
		'3 validator units on every action (custom_python or a parameterised text check = 2, a bare presence check = 1)',
	] },
	hardened: { label: 'Hardened', gates: [
		'One passing run signed by another account, on a device fingerprint the author has not recorded on',
		'2 or more OEM or Android-major combinations',
		'Bench on 2 or more models',
		'10 or more community runs with Wilson lower bound (95%) of 0.80 or higher',
		'"Known failure modes" section in the docs',
		'Re-verified in the last 90 days',
	] },
	reference: { label: 'Reference', gates: [
		'Hardened for 60 or more continuous days',
		'Curator review',
		'No open P1 bug older than 14 days',
		'Author at Contributor tier or above',
		'Capped at about 5% of Hardened skills per category; re-reviewed every 180 days or on a major target-app release',
	] },
};

export const TIERS: { id: Tier; label: string; points: number; gates: string[] }[] =
	TIER_IDS.map((id) => ({ id, label: TIER_COPY[id].label, points: SCORING.thresholds[id], gates: TIER_COPY[id].gates }));

export const TIER_INDEX: Record<Tier, number> = Object.fromEntries(TIERS.map((t, i) => [t.id, i])) as Record<Tier, number>;

/** Normalise a registry tier string. `verified` was the pre-rename name of
 *  `proven` (renamed so it cannot be confused with the Verified trust tier). */
export function isLadderTier(raw: string | undefined): boolean {
	const t = (raw ?? '').toLowerCase();
	return t === 'verified' || t in TIER_INDEX;
}

export function normalizeTier(raw: string | undefined): Tier {
	const t = (raw ?? 'draft').toLowerCase();
	if (t === 'verified') return 'proven';
	return (t in TIER_INDEX ? t : 'draft') as Tier;
}

const CATEGORY_COPY: Record<string, { label: string; earnedBy: string }> = {
	docs: { label: 'Docs and packaging', earnedBy: 'Manifest, README, a known-failure-modes section, demos, a before/after pair recording' },
	self_evidence: { label: 'Self-evidence', earnedBy: 'Your first verified self-run, validator units on your weakest action, a bench on one model, your own passing runs on a second device, and self-reliability: the Wilson lower bound over all your own verified runs once every action has 3 or more' },
	independent: { label: 'Independent verification', earnedBy: 'Signed runs by other accounts on other device classes, benches on more models' },
	community_usage: { label: 'Community usage (90 days)', earnedBy: 'Wilson lower bound of the success rate over recent recorded runs, once enough runs exist' },
	usage: { label: 'Community usage (90 days)', earnedBy: 'Wilson lower bound of the success rate over recent recorded runs, once enough runs exist' },
	maintenance: { label: 'Maintenance', earnedBy: 'Keeping the skill current: re-verification after target-app releases, fixing reported breakage' },
};

const titleCase = (id: string) => id.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

/** Registry `quality.categories` keys that predate the 0-100 file. */
export const CATEGORY_ALIASES: Record<string, string[]> = { community_usage: ['usage'] };

const ITEM_LABEL: Record<string, string> = {
	self_reliability: 'Self-reliability (your own pass rate)',
	validators: 'Validators (per action)',
	first_self_run: 'First self-run',
	bench_one_model: 'Bench on one model',
	demo_any: 'Demo clip',
	demo_all_actions: 'Demo for every action',
	failure_modes: 'Known failure modes',
	before_after: 'Before / after pair (clip + metrics)',
	self_second_device: 'Second device of your own (every action)',
};

export const CATEGORIES: { id: string; label: string; cap: number; earnedBy: string; items: [string, string][] }[] =
	SCORING.categories.map((c) => ({
		id: c.id,
		cap: c.cap,
		label: CATEGORY_COPY[c.id]?.label ?? titleCase(c.id),
		earnedBy: CATEGORY_COPY[c.id]?.earnedBy ?? '',
		items: [
			...c.items.map(([k, v]) => [ITEM_LABEL[k] ?? titleCase(k), `+${v}`] as [string, string]),
			...c.rules.map(([k, rule]) => [ITEM_LABEL[k] ?? titleCase(k), rule] as [string, string]),
		],
	}));

export const SELF_RELIABILITY = SCORING.selfReliability;

/** Scoring v1.2: plain-sentence rules shipped in the scoring file, rendered verbatim. Empty on older files. */
export const SCORING_RULES: string[] = Array.isArray(SCORING.raw.rules)
	? (SCORING.raw.rules as unknown[]).filter((r): r is string => typeof r === 'string' && r.trim().length > 0)
	: [];

/** Scoring v1.2: maintenance points decay linearly to 0 this many days after the last non-self passing run. */
export const MAINTENANCE_DECAY_DAYS: number | null = (() => {
	const m = (SCORING.raw.categories as Record<string, any> | undefined)?.maintenance;
	return typeof m?.decay_days === 'number' ? m.decay_days : null;
})();
export const VALIDATOR_RULE = SCORING.validatorRule;

/** Points a registry entry earned in a category, honouring old key names. */
export function categoryPoints(cats: Record<string, number> | undefined, id: string): number {
	if (!cats) return 0;
	for (const key of [id, ...(CATEGORY_ALIASES[id] ?? [])]) if (typeof cats[key] === 'number') return cats[key];
	return 0;
}

export const FRESHNESS: [string, string][] = [
	['Re-verified within 90 days', 'x1.0'],
	['90 to 180 days', 'x0.8, marked Stale'],
	['Over 180 days', 'x0.5'],
	['Failing run on a newer app version than the last pass', 'Planned (not enforced yet): tier frozen within 24 h until a pass arrives'],
];

/** Prefix on every listed rule the registry does not enforce today. Keep it until the code exists. */
export const PLANNED_PREFIX = 'Planned (not enforced yet): ';

export const ANTI_GAMING: string[] = [
	'Downloads and likes are shown but are worth 0 points.',
	'Points attach only to signed run artifacts that verify against a published key.',
	'Self-runs never count as independent. A verification signed by a maintainer-held key is shown as a maintainer-signed replay, not as independent.',
	`${PLANNED_PREFIX}reciprocal verification pairs stop counting after the 3rd pair in 30 days.`,
	'One device fingerprint is one report, however many accounts submit it.',
	`${PLANNED_PREFIX}accounts younger than 14 days cannot confer verification points.`,
	`${PLANNED_PREFIX}a random 5% of Hardened and Reference skills are re-executed every month.`,
	'Pages show raw passed/run counts per evidence class. The leaderboard ranks by points, then tier; a Wilson lower bound with a 10 pass / 10 fail prior only breaks ties and is never shown as a rate.',
	'Tier changes show as provisional for 7 days.',
	'Point values change only at season boundaries, with 30 days notice.',
	`${PLANNED_PREFIX}\`generated_with:\` is required; undisclosed AI generation freezes points for 30 days.`,
];

export const TRUST: Record<Trust, { label: string; blurb: string }> = {
	official: { label: 'Official', blurb: 'Written and maintained by the Ghost team under skillhub/ghost/. Says who wrote it, not that anyone else verified it; the Reliability card shows the runs. Installs silently.' },
	verified: { label: 'Verified', blurb: 'Community skill merged into the hub repo through a recorded review.' },
	benchmark: { label: 'Benchmark', blurb: 'Reference skill imported from a benchmark suite (AndroidWorld) by the maintainers. Not reviewed community code; most are scaffolds with no authored steps yet.' },
	unverified: { label: 'Unverified', blurb: 'No recorded review: installed from a URL outside the hub repo, or merged without one. The CLI asks before installing.' },
	quarantined: { label: 'Quarantined', blurb: 'Flagged by the registry. Install is blocked unless forced.' },
};

/** Wilson score interval lower bound. z = 1.96 for 95%. */
export function wilsonLower(passed: number, total: number, z = 1.96): number {
	if (total <= 0) return 0;
	const p = passed / total;
	const z2 = z * z;
	const denom = 1 + z2 / total;
	const centre = p + z2 / (2 * total);
	const margin = z * Math.sqrt((p * (1 - p) + z2 / (4 * total)) / total);
	return Math.max(0, (centre - margin) / denom);
}

/** Leaderboard tie-break only: Wilson LB on runs plus the Bayesian prior (10 pass / 10 fail).
 *  Never shown as a rate; pages show raw counts and, as a secondary line, the prior-free floor. */
export function displayRating(passed: number, total: number): number {
	return wilsonLower(passed + 10, total + 20);
}

/** "Confidence floor" copy: the prior-free 95% Wilson lower bound, as a percent string, or null. */
export function confidenceFloor(passed: number, total: number): string | null {
	if (total <= 0) return null;
	return `${Math.round(wilsonLower(passed, total) * 100)}%`;
}

/** Days between two ISO timestamps (b defaults to a reference "now"). */
export function daysBetween(aIso: string, bIso: string): number {
	return (Date.parse(bIso) - Date.parse(aIso)) / 86_400_000;
}

export function freshnessLabel(lastVerified: string | null, nowIso: string): { label: string; stale: boolean } {
	if (!lastVerified) return { label: 'No counted run yet', stale: true };
	const d = daysBetween(lastVerified, nowIso);
	if (d <= 90) return { label: `Last counted run ${Math.max(0, Math.round(d))} days ago`, stale: false };
	if (d <= 180) return { label: `Stale: last counted run ${Math.round(d)} days ago`, stale: true };
	return { label: `Stale: last counted run ${Math.round(d)} days ago`, stale: true };
}
