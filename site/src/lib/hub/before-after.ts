// Before / after pair metrics: `demos/before-after.json` (schema 1) next to `demos/before-after.<webm|mp4|gif>`.
// One recorded pair of the same prompt on the same phone, once without the skill (the agent drives the UI by hand)
// and once with it (find_skill + run_skill). Never run evidence (scoring may count the pair as a docs item).

export interface BeforeAfterSide { seconds: number; tokens: number; tool_calls: number; ok: boolean }

/** What `ok` was measured against: an independent check of the final phone state, or only that the agent finished its turn. */
export type OkMeans = 'verified_task_check' | 'agent_finished_turn';

export interface BeforeAfterMetrics {
	schema_version: 1;
	action: string | null;
	prompt: string | null;
	model: string | null;
	device: string | null;
	recorded: string | null;
	ok_means: OkMeans;
	before: BeforeAfterSide;
	after: BeforeAfterSide;
	notes: string | null;
	source: string | null;
}

export interface BeforeAfterSummary {
	/** "11.8× fewer tokens" | "1.4× more tokens" | "about the same tokens" */
	tokens: string;
	/** "4× faster" | "1.3× slower" | "about the same time" */
	time: string;
	/** "18 → 5 tool calls" */
	calls: string;
	/** `${tokens}, ${time}` */
	headline: string;
	/** Plain-language result of both sides, worded by what `ok` means. */
	outcome: string;
	tokensFewer: boolean;
	faster: boolean;
}

const OK_MEANS: OkMeans[] = ['verified_task_check', 'agent_finished_turn'];
const SAME_BAND = 0.05; // within 5 % either way reads as "about the same"

function side(raw: unknown, name: string, fail: (m: string) => void): BeforeAfterSide | null {
	if (!raw || typeof raw !== 'object') { fail(`\`${name}\` is missing`); return null; }
	const s = raw as Record<string, unknown>;
	for (const k of ['seconds', 'tokens', 'tool_calls'] as const) {
		if (typeof s[k] !== 'number' || !Number.isFinite(s[k]) || (s[k] as number) < 0) { fail(`\`${name}.${k}\` must be a number >= 0`); return null; }
	}
	if (typeof s.ok !== 'boolean') { fail(`\`${name}.ok\` must be true or false`); return null; }
	return { seconds: s.seconds as number, tokens: s.tokens as number, tool_calls: s.tool_calls as number, ok: s.ok };
}

function optText(v: unknown): string | null {
	return typeof v === 'string' && v.trim() ? v : null;
}

/** Validate the registry's `before_after.metrics` value. Returns null (and warns once) on any malformed field,
 *  so a bad numbers file never breaks the build or shows a wrong figure: the clip still plays without numbers. */
export function normalizeBeforeAfter(raw: unknown, warn: (m: string) => void = () => {}): BeforeAfterMetrics | null {
	if (raw == null) return null;
	let bad: string | null = null;
	const fail = (m: string) => { bad ??= m; };
	if (typeof raw !== 'object') { warn('must be an object'); return null; }
	const r = raw as Record<string, unknown>;
	if (r.schema_version !== 1) fail('schema_version must be 1');
	const before = side(r.before, 'before', fail), after = side(r.after, 'after', fail);
	const okMeans = r.ok_means ?? 'verified_task_check';
	if (!OK_MEANS.includes(okMeans as OkMeans)) fail(`ok_means must be one of ${OK_MEANS.join(', ')}`);
	if (bad || !before || !after) { warn(bad ?? 'invalid'); return null; }
	return {
		schema_version: 1,
		action: optText(r.action), prompt: optText(r.prompt), model: optText(r.model), device: optText(r.device),
		recorded: optText(r.recorded), ok_means: okMeans as OkMeans, before, after, notes: optText(r.notes), source: optText(r.source),
	};
}

/** 11.76 → "11.8×", 4.02 → "4×", 23.4 → "23×". */
export function formatRatio(x: number): string {
	if (!Number.isFinite(x) || x <= 0) return '–';
	const v = x >= 20 ? Math.round(x) : Math.round(x * 10) / 10;
	return `${Number.isInteger(v) ? v : v.toFixed(1)}×`;
}

export function formatSeconds(s: number): string {
	return s >= 100 ? `${Math.round(s)} s` : `${s.toFixed(1)} s`;
}

export function formatCount(n: number): string {
	return n.toLocaleString('en-US');
}

function ratioText(before: number, after: number, less: string, more: string, same: string): { text: string; better: boolean } {
	if (!before || !after) return { text: same, better: false };
	const r = before / after;
	if (r >= 1 + SAME_BAND) return { text: `${formatRatio(r)} ${less}`, better: true };
	if (r <= 1 - SAME_BAND) return { text: `${formatRatio(1 / r)} ${more}`, better: false };
	return { text: same, better: false };
}

export function summarizeBeforeAfter(m: BeforeAfterMetrics): BeforeAfterSummary {
	const tokens = ratioText(m.before.tokens, m.after.tokens, 'fewer tokens', 'more tokens', 'about the same tokens');
	const time = ratioText(m.before.seconds, m.after.seconds, 'faster', 'slower', 'about the same time');
	const verdict = (ok: boolean) => m.ok_means === 'verified_task_check' ? (ok ? 'passed' : 'failed') : (ok ? 'finished' : 'stopped early');
	const outcome = m.ok_means === 'verified_task_check'
		? `Task check: ${verdict(m.before.ok)} without the skill, ${verdict(m.after.ok)} with it.`
		: `Agent run: ${verdict(m.before.ok)} without the skill, ${verdict(m.after.ok)} with it (not independently checked).`;
	return {
		tokens: tokens.text, time: time.text,
		calls: `${formatCount(m.before.tool_calls)} → ${formatCount(m.after.tool_calls)} tool calls`,
		headline: `${tokens.text}, ${time.text}`,
		outcome, tokensFewer: tokens.better, faster: time.better,
	};
}
