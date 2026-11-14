// Bench card data: `<skill dir>/bench/*.json` (androidworld or ghost-native), written by
// `ghost skill bench --androidworld` (gitd/skills/engine/bench.py write_summary)
// and, for the agent arms, tools/bench/agent_arm.py. Display only: nothing here
// feeds the score. Shape (v1 agreed 2026-10-20, v2 episodes confirmed by
// bench runner 2026-10-22, the benchmark episode contract):
//
// {
//   "suite": "androidworld", "generated_at": "<iso>", "upstream_commit": "<sha>",
//   "protocol": "docs/benchmark-protocol.md",
//   "evidence_class": "maintainer", "label": "maintainer-run, not independent",
//   "model": ["claude-haiku-5-5"], "source": "bench/agent-runs/ab4.json", "run_ids": ["ab3", "ab4"],
//   // generated_at is UTC conversion time, not the episode execution date.
//   // Suites include androidworld and ghost-native; source is the latest import.
//   "tasks": [{
//     "task_id": "ExpenseAddMultipleFromMarkor", "action": "expense_add_multiple_from_markor", "seeds": 5,
//     "label": "Expense: reimbursable rows from Markor",
//     "source": "bench/agent-runs/ab1.json", "generated_at": "<UTC iso>", "run_ids": ["ab1"],
//     "stats": {
//       "arms": {"before": {"passed": 2, "total": 5, "wilson95": [0.1176, 0.7693],
//         "model": ["claude-haiku-5-5"], "tokens": {"median": 41000, "q1": 30000, "q3": 50000, "n": 5},
//         "wall_ms": {"median": 312000, "q1": 300000, "q3": 330000, "n": 5},
//         "llm_calls": {"median": 25, "q1": 24, "q3": 25, "n": 5},
//         "ui_actions": {"median": 20, "q1": 18, "q3": 22, "n": 5}, "tool_errors": 1}},
//       "paired": {"after_mcp_vs_before": {"pairs": 5, "only_before_passed": 0,
//         "only_after_passed": 3, "mcnemar_exact_p": 0.25, "tokens_saved_median": 32000}}
//     },
//     // labelled_results preserves historical findings and may carry its own episodes[].
//     // These episodes never enter the current task arms/episodes aggregates.
//     "arms": {                      // VALID arms only (each may carry "valid": true)
//       "before":       {"passed": 2, "total": 5, "wall_ms_median": 312000, "tokens_median": 41000},
//       "after_replay": {"passed": 5, "total": 5, "wall_ms_median": 38000,  "tokens_median": 0},
//       "after_mcp":    {"passed": 5, "total": 5, "wall_ms_median": 95000,  "tokens_median": 9000}
//     },
//     "void_arms": {                 // measurements that are NOT results: never rendered as numbers
//       "before": {"passed": 0, "total": 3, "valid": false, "invalid_reason": "task app was uninstalled ..."}
//     },
//     "episodes": [{                 // one row per (arm, seed); agent arms carry calls[]
//       "arm": "before", "seed": 30, "model": "claude-haiku-5-5", "pass": false, "valid": true,
//       "tokens": 41230, "tokens_in": 38000, "tokens_out": 3230, "tokens_cache_read": 0, "wall_ms": 312000,
//       "steps": 27, "llm_calls": 27, "skill_calls": 0, "tool_errors": 1,
//       "ui_actions": {"tap": 12, "type": 4, "swipe": 2, "key": 1, "launch": 1, "total": 20},
//       "actions": [{"i": 1, "type": "launch", "tool": "launch_app", "ok": true}],
//       "calls":   [{"i": 1, "tokens_in": 1800, "tokens_out": 120, "tokens_cache_read": 0}],
//       "trace": "bench/agent-runs/ab1/before-30.jsonl"
//     }]
//   }]
// }
// Every arm and episode may carry skill_sha + skill_version, e.g.
// "skill_sha": "a1980cff (feat/skillhub 1b3f8e66)", "skill_version": "0.1.0".
// Existing concrete arm SHAs win; pre-fix/native revisions are inferred from git
// history at run time, not digest-bound execution attestations. For before arms,
// these fields identify the comparison skill revision (no skill was installed).
// Adjudicated ITT failures use valid:true, pass:false and counted_as (explanation),
// with original source_valid/source_invalid_reason retained separately. Historical
// findings may retain valid:false plus counted:true/counting_rule:"intention-to-treat";
// these never enter the current pool. Other invalid rows remain void. Incompatible source arm/paired stats are omitted
// when enriching a published ITT arm; its published passed/total/medians remain.
// Arms and episodes may carry skill_sha and skill_version for the version that ran.
// Never substitute the currently installed skill version for missing run provenance.
// Top-level provenance: evidence_class, label, model (string or string[]),
// generated_at, source, run_ids. Tasks may override source/generated_at/run_ids.
// tasks[].labelled_results is a dictionary keyed by result name; each value may
// carry episodes[] in the same shape (including valid:false). Those episodes are
// displayed within their labelled result, never pooled into current arm results.
// Unknown fields and arms are ignored. An arm or episode with `valid: false` is
// listed as void with its reason and never counted.

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

export type BenchArm = 'before' | 'after_replay' | 'after_mcp';
export const BENCH_ARMS: { id: BenchArm; label: string; blurb: string }[] = [
	{ id: 'before', label: 'Agent alone', blurb: 'The agent solves the task cold, no skill installed.' },
	{ id: 'after_replay', label: 'Skill replay', blurb: 'The skill replays deterministically, no model in the loop.' },
	{ id: 'after_mcp', label: 'Agent + skill', blurb: 'The agent has the skill as a tool and decides to use it.' },
];
const ARM_IDS = new Set<string>(BENCH_ARMS.map((a) => a.id));

export interface BenchVersion { skillSha?: string | null; skillVersion?: string | null; model?: string | null; generatedAt?: string | null }
export interface BenchArmResult extends BenchVersion { passed: number; total: number; wall_ms_median?: number | null; tokens_median?: number | null }
export interface VoidArm extends BenchVersion { arm: BenchArm; total: number; reason: string }
export interface BenchAction { i: number; type: string; tool: string | null; ok: boolean | null }
export interface BenchCall { i: number; tokens_in: number | null; tokens_out: number | null; tokens_cache_read: number | null }
export interface BenchEpisode extends BenchVersion {
	arm: BenchArm; seed: number | string | null; model: string | null; pass: boolean; valid: boolean; countedAs: string | null; counted: boolean | null; countingRule: string | null; invalidReason: string | null;
	tokens: number | null; tokensIn: number | null; tokensOut: number | null; tokensCacheRead: number | null;
	wallMs: number | null; steps: number | null; llmCalls: number | null; skillCalls: number | null; toolErrors: number | null;
	uiActions: { tap: number; type: number; swipe: number; key: number; launch: number; total: number } | null;
	actions: BenchAction[]; calls: BenchCall[]; trace: string | null;
}
export interface ArmStats { wilson95: [number, number] | null; models: string[]; tokensMedian: number | null; tokensQ1: number | null; tokensQ3: number | null; uiActionsMedian: number | null; wallMsMedian: number | null; llmCallsMedian: number | null; toolErrors: number | null }
export interface PairedStats { key: string; pairs: number; onlyBeforePassed: number; onlyAfterPassed: number; mcnemarExactP: number | null; tokensSavedMedian: number | null }
export interface BenchTask {
	task_id: string; label: string | null; source: string | null; generatedAt: string | null; runIds: string[]; labelledResults: { key: string; label: string; note: string | null; model: string | null; result: BenchArmResult | null; episodes: BenchEpisode[] }[]; action?: string | null; seeds?: number;
	arms: Partial<Record<BenchArm, BenchArmResult>>;
	voidArms: VoidArm[];
	episodes: BenchEpisode[];
	/** tasks[].stats from the bench (Wilson 95% CI per arm, paired McNemar); display only. */
	stats: { arms: Partial<Record<BenchArm, ArmStats>>; paired: PairedStats[] };
	/** after_replay (or after_mcp) pass rate minus before pass rate, in [-1, 1]; null without both arms. */
	delta: number | null;
	/** Median LLM calls per episode for before and after_mcp (valid episodes only); the "calls 27 -> 3" headline. */
	callsHeadline: { before: number; after: number } | null;
}
export interface BenchSummary {
	suite: string; evidenceClass: string | null; label: string; model: string | null; source: string | null; runIds: string[]; generatedAt: string | null; upstreamCommit: string | null; protocol: string | null;
	tasks: BenchTask[];
	/** Arms present (valid) in at least one task, in BENCH_ARMS order. */
	arms: BenchArm[];
	hasEpisodes: boolean;
}

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const int = (v: unknown): number => Math.max(0, Math.round(num(v) ?? 0));
const str = (v: unknown, re = /^[\w .:/@()+,-]{1,200}$/): string | null => (typeof v === 'string' && re.test(v) ? v : null);
const models = (v: unknown): string | null => (Array.isArray(v) ? v : [v]).map((m) => str(m, /^[\w.:/-]{1,64}$/)).filter(Boolean).join(', ') || null;
const iso = (v: unknown) => typeof v === 'string' && !Number.isNaN(Date.parse(v)) ? new Date(v).toISOString() : null;
const runIds = (v: unknown): string[] => (Array.isArray(v) ? v : []).map((s) => str(s)).filter((s): s is string => !!s);
const textLabel = (v: unknown): string | null => typeof v === 'string' && v.trim() ? v.trim().slice(0, 1000) : null;
const REPO_PATH = /^(?!\/)(?!.*\.\.)[\w./-]{1,200}$/;

function version(o: Record<string, unknown>): BenchVersion {
	return Object.fromEntries(Object.entries({ skillSha: str(o.skill_sha), skillVersion: str(o.skill_version), model: models(o.model), generatedAt: iso(o.generated_at) }).filter(([, value]) => value != null)) as BenchVersion;
}

/** The converter publishes counted ITT failures as valid:true, pass:false. */
export function countedEpisode(e: BenchEpisode): boolean { return e.valid; }

/** Historical adjudications are shown only inside their labelled finding. */
export function labelledEpisodeOutcome(e: BenchEpisode): string {
	if (e.valid) return e.pass ? 'pass' : e.countedAs ?? 'fail';
	if (!e.pass && e.counted === true && e.countingRule === 'intention-to-treat') {
		return `fail (intention-to-treat; source marked invalid): ${e.invalidReason ?? 'episode capped'}`;
	}
	return `void: ${e.invalidReason ?? 'marked invalid by the bench'}`;
}

/** Translate raw arm IDs within supplied historical labels without changing their meaning. */
export function humanBenchText(text: string): string {
 const labels = Object.fromEntries(BENCH_ARMS.map(({ id, label }) => [id, label]));
 return text.replace(/\b(after_mcp|after_replay)\b/g, (id) => labels[id]);
}

/** Public labels for paired arm comparisons; retain unknown comparisons readably. */
export function pairedLabel(key: string): string {
 const labels = Object.fromEntries(BENCH_ARMS.map(({ id, label }) => [id, label]));
 return key.split('_vs_').map((arm) => labels[arm] ?? arm.replaceAll('_', ' ')).join(' vs ').replace('vs Agent alone', 'vs agent alone');
}

export function fmtSkillVersion(v: BenchVersion | undefined): string {
	return `skill version: ${v?.skillVersion ?? 'not recorded'} · SHA: ${v?.skillSha ?? 'not recorded'}`;
}

export function median(xs: number[]): number | null {
	if (xs.length === 0) return null;
	const s = [...xs].sort((a, b) => a - b);
	const m = s.length >> 1;
	return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function arm(raw: unknown): BenchArmResult | null {
	if (!raw || typeof raw !== 'object') return null;
	const o = raw as Record<string, unknown>;
	if (o.valid === false) return null;
	const passed = num(o.passed), total = num(o.total);
	if (passed == null || total == null || total <= 0 || !Number.isInteger(total) || !Number.isInteger(passed) || passed < 0 || passed > total) return null;
	return { ...version(o), passed, total, wall_ms_median: num(o.wall_ms_median), tokens_median: num(o.tokens_median) };
}

function voidArm(id: string, raw: unknown): VoidArm | null {
	if (!ARM_IDS.has(id) || !raw || typeof raw !== 'object') return null;
	const o = raw as Record<string, unknown>;
	const reason = typeof o.invalid_reason === 'string' && o.invalid_reason.trim() ? o.invalid_reason.trim().slice(0, 400) : 'marked invalid by the bench';
	return { ...version(o), arm: id as BenchArm, total: int(o.total), reason };
}

function episode(raw: unknown): BenchEpisode | null {
	if (!raw || typeof raw !== 'object') return null;
	const o = raw as Record<string, any>;
	if (!ARM_IDS.has(String(o.arm)) || typeof o.pass !== 'boolean') return null;
	const ui = o.ui_actions && typeof o.ui_actions === 'object' ? o.ui_actions : null;
	const actions: BenchAction[] = (Array.isArray(o.actions) ? o.actions : []).flatMap((a: any, idx: number) => {
		if (!a || typeof a !== 'object') return [];
		const type = str(a.type, /^[a-z_]{1,24}$/);
		if (!type) return [];
		return [{ i: num(a.i) ?? idx + 1, type, tool: str(a.tool, /^[\w.-]{1,64}$/), ok: typeof a.ok === 'boolean' ? a.ok : null }];
	});
	const calls: BenchCall[] = (Array.isArray(o.calls) ? o.calls : []).flatMap((c: any, idx: number) => {
		if (!c || typeof c !== 'object') return [];
		return [{ i: num(c.i) ?? idx + 1, tokens_in: num(c.tokens_in), tokens_out: num(c.tokens_out), tokens_cache_read: num(c.tokens_cache_read) }];
	});
	return {
		...version(o), arm: o.arm, seed: num(o.seed) ?? str(o.seed, /^[\w-]{1,32}$/), model: str(o.model, /^[\w.:/-]{1,64}$/),
		pass: o.pass === true, valid: o.valid !== false, countedAs: textLabel(o.counted_as), counted: typeof o.counted === 'boolean' ? o.counted : null, countingRule: str(o.counting_rule),
		invalidReason: o.valid === false ? (typeof o.invalid_reason === 'string' ? o.invalid_reason.slice(0, 400) : 'marked invalid by the bench') : null,
		tokens: num(o.tokens), tokensIn: num(o.tokens_in), tokensOut: num(o.tokens_out), tokensCacheRead: num(o.tokens_cache_read),
		wallMs: num(o.wall_ms), steps: num(o.steps), llmCalls: num(o.llm_calls) ?? (calls.length || null), skillCalls: num(o.skill_calls), toolErrors: num(o.tool_errors),
		uiActions: ui ? { tap: int(ui.tap), type: int(ui.type), swipe: int(ui.swipe), key: int(ui.key), launch: int(ui.launch), total: int(ui.total) || int(ui.tap) + int(ui.type) + int(ui.swipe) + int(ui.key) + int(ui.launch) } : null,
		actions, calls, trace: typeof o.trace === 'string' && REPO_PATH.test(o.trace) ? o.trace : null,
	};
}

function parseStats(raw: unknown): BenchTask['stats'] {
	const out: BenchTask['stats'] = { arms: {}, paired: [] };
	if (!raw || typeof raw !== 'object') return out;
	const o = raw as Record<string, any>;
	const armsRaw = o.arms && typeof o.arms === 'object' ? o.arms : {};
	for (const { id } of BENCH_ARMS) {
		const a = armsRaw[id];
		if (!a || typeof a !== 'object') continue;
		const w = Array.isArray(a.wilson95) && a.wilson95.length === 2 && num(a.wilson95[0]) != null && num(a.wilson95[1]) != null && a.wilson95[0] >= 0 && a.wilson95[1] <= 1 && a.wilson95[0] <= a.wilson95[1] ? [a.wilson95[0], a.wilson95[1]] as [number, number] : null;
		const med = (x: any) => (x && typeof x === 'object' ? num(x.median) : num(x));
		out.arms[id] = {
			wilson95: w,
			models: (Array.isArray(a.model) ? a.model : [a.model]).map((m: unknown) => str(m, /^[\w.:/-]{1,64}$/)).filter((m): m is string => !!m),
			tokensMedian: med(a.tokens), tokensQ1: num(a.tokens?.q1), tokensQ3: num(a.tokens?.q3), uiActionsMedian: med(a.ui_actions), wallMsMedian: med(a.wall_ms), llmCallsMedian: med(a.llm_calls), toolErrors: num(a.tool_errors),
		};
	}
	const pairedRaw = o.paired && typeof o.paired === 'object' ? o.paired : {};
	for (const [key, v] of Object.entries(pairedRaw)) {
		if (!v || typeof v !== 'object' || !/^[a-z_]+_vs_[a-z_]+$/.test(key)) continue;
		const pr = v as Record<string, unknown>;
		out.paired.push({ key, pairs: int(pr.pairs), onlyBeforePassed: int(pr.only_before_passed), onlyAfterPassed: int(pr.only_after_passed), mcnemarExactP: num(pr.mcnemar_exact_p), tokensSavedMedian: num(pr.tokens_saved_median) });
	}
	return out;
}

export function rate(a: BenchArmResult | undefined | null): number | null {
	return a && a.total > 0 ? a.passed / a.total : null;
}

/** Parse and validate a bench file. Returns null when it is not usable; bad rows are dropped. */
export function normalizeBench(raw: unknown, warn: (m: string) => void = () => {}): BenchSummary | null {
	if (!raw || typeof raw !== 'object') { warn('bench file is not an object'); return null; }
	const o = raw as Record<string, unknown>;
	const suite = String(o.suite ?? '');
	if (suite !== 'androidworld' && suite !== 'ghost-native') { warn(`bench suite ${JSON.stringify(o.suite)} is not supported`); return null; }
	const tasks: BenchTask[] = [];
	for (const t of Array.isArray(o.tasks) ? o.tasks : []) {
		if (!t || typeof t !== 'object') continue;
		const row = t as Record<string, unknown>;
		const task_id = String(row.task_id ?? '').trim();
		if (!/^[A-Za-z0-9_.-]{1,80}$/.test(task_id)) { warn(`bench task id ${JSON.stringify(row.task_id)} skipped`); continue; }
		const armsRaw = (row.arms && typeof row.arms === 'object' ? row.arms : {}) as Record<string, unknown>;
		const arms: BenchTask['arms'] = {};
		const voidArms: VoidArm[] = [];
		for (const { id } of BENCH_ARMS) {
			const a = arm(armsRaw[id]);
			if (a) arms[id] = a;
			else if (armsRaw[id] && typeof armsRaw[id] === 'object' && (armsRaw[id] as any).valid === false) { const v = voidArm(id, armsRaw[id]); if (v) voidArms.push(v); }
		}
		// void_arms = earlier measurements that were discarded; a valid arm of the same name (a re-run) stays.
		const voidRaw = (row.void_arms && typeof row.void_arms === 'object' ? row.void_arms : {}) as Record<string, unknown>;
		for (const [id, v] of Object.entries(voidRaw)) {
			const va = voidArm(id, v);
			if (va && !voidArms.some((x) => x.arm === va.arm)) voidArms.push(va);
		}
		const episodes = (Array.isArray(row.episodes) ? row.episodes : []).map(episode).filter((e): e is BenchEpisode => !!e);
		if (Object.keys(arms).length === 0 && voidArms.length === 0 && episodes.length === 0) { warn(`bench task ${task_id} has no valid arm`); continue; }
		const before = rate(arms.before);
		const after = rate(arms.after_replay) ?? rate(arms.after_mcp);
		const callsOf = (armId: BenchArm) => median(episodes.filter((e) => e.arm === armId && e.valid && e.llmCalls != null).map((e) => e.llmCalls as number));
		const cb = callsOf('before'), ca = callsOf('after_mcp');
		tasks.push({
			task_id,
			label: textLabel(row.label),
			source: typeof row.source === 'string' && REPO_PATH.test(row.source) ? row.source : null,
			generatedAt: iso(row.generated_at), runIds: runIds(row.run_ids),
			labelledResults: Object.entries(row.labelled_results && typeof row.labelled_results === 'object' ? row.labelled_results : {}).flatMap(([key, value]) => {
				if (!value || typeof value !== 'object') return [];
				const v = value as Record<string, unknown>;
				return [{ key, label: textLabel(v.label) ?? key, note: textLabel(v.note), model: models(v.model), result: arm(v), episodes: (Array.isArray(v.episodes) ? v.episodes : []).map(episode).filter((e): e is BenchEpisode => !!e) }];
			}),
			action: typeof row.action === 'string' && /^[a-z][a-z0-9_-]{0,63}$/.test(row.action) ? row.action : null,
			seeds: num(row.seeds) ?? undefined,
			arms, voidArms, episodes,
			stats: parseStats(row.stats),
			delta: before != null && after != null ? after - before : null,
			callsHeadline: cb != null && ca != null ? { before: cb, after: ca } : null,
		});
	}
	if (tasks.length === 0) return null;
	const present = new Set(tasks.flatMap((t) => Object.keys(t.arms) as BenchArm[]));
	return {
		suite,
		evidenceClass: str(o.evidence_class),
		label: textLabel(o.label) ?? 'maintainer-run, not independent',
		model: models(o.model), runIds: runIds(o.run_ids),
		source: typeof o.source === 'string' && REPO_PATH.test(o.source) ? o.source : null,
		generatedAt: iso(o.generated_at),
		upstreamCommit: typeof o.upstream_commit === 'string' && /^[0-9a-f]{7,40}$/.test(o.upstream_commit) ? o.upstream_commit : null,
		protocol: typeof o.protocol === 'string' && REPO_PATH.test(o.protocol) ? o.protocol : null,
		tasks,
		arms: BENCH_ARMS.map((a) => a.id).filter((a) => present.has(a)),
		hasEpisodes: tasks.some((t) => t.episodes.length > 0),
	};
}

/** Read all supported suites, keeping malformed files isolated. */
export function readBenches(skillDir: string | null, warn: (m: string) => void = () => {}): BenchSummary[] {
	if (!skillDir) return [];
	const dir = join(skillDir, 'bench');
	if (!existsSync(dir)) return [];
	try {
		return readdirSync(dir).filter((name) => name.endsWith('.json')).sort().flatMap((name) => {
			try {
				const b = normalizeBench(JSON.parse(readFileSync(join(dir, name), 'utf8')), warn);
				return b ? [b] : [];
			} catch (e) { warn(`bench ${name} unreadable: ${(e as Error).message}`); return []; }
		});
	} catch (e) { warn(`bench directory unreadable: ${(e as Error).message}`); return []; }
}

/** Compatibility for consumers of the original AndroidWorld-only loader. */
export function readBench(skillDir: string | null, warn: (m: string) => void = () => {}): BenchSummary | null {
	return readBenches(skillDir, warn).find((b) => b.suite === 'androidworld') ?? null;
}

export function passText(result: BenchArmResult | undefined, ci?: [number, number] | null): string {
	if (!result) return 'pending';
	return `${result.passed}/${result.total} · ${ci ? `Wilson 95% CI ${ci[0].toFixed(3)}–${ci[1].toFixed(3)}` : 'no CI'}`;
}

export function fmtDelta(d: number | null): { text: string; cls: 'delta-up' | 'delta-down' | 'delta-flat' } {
	if (d == null) return { text: '', cls: 'delta-flat' };
	const pts = Math.round(d * 100);
	if (pts > 0) return { text: `+${pts} pts`, cls: 'delta-up' };
	if (pts < 0) return { text: `${pts} pts`, cls: 'delta-down' };
	return { text: '±0', cls: 'delta-flat' };
}

export function fmtWall(ms: number | null | undefined): string {
	if (ms == null) return '';
	if (ms < 1000) return `${Math.round(ms)} ms`;
	if (ms < 90_000) return `${(ms / 1000).toFixed(0)} s`;
	return `${(ms / 60_000).toFixed(1)} min`;
}

export function fmtTokens(n: number | null | undefined): string {
	if (n == null) return '';
	if (n < 1000) return String(Math.round(n));
	if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`;
	return `${(n / 1_000_000).toFixed(2)}M`;
}
