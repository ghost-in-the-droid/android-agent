// Build-time loader for the Skill Hub registry.
//
// Reads `skillhub/registry.json` + `skillhub/registry/index/<author>.<slug>.json`
// (contract section 3 + Amendment A) from the repo root. When the real files are
// not generated yet, falls back to `tools/fixtures/registry-sample.json` +
// `tools/fixtures/registry/index/*.json` and every page shows a preview banner.
//
// Override the hub root with HUB_DIR=/path/to/skillhub.

import type { ActionState } from './states';
import type { DeviceGrid } from './device-grid';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { isAbsolute, join, normalize, resolve, sep } from 'node:path';
import { RESERVED_AUTHOR_NAMES, RECENT_WINDOW_DAYS } from './config';
import { TIER_INDEX, daysBetween, displayRating, isLadderTier, normalizeTier, wilsonLower, type Tier, type Trust } from './scoring';
import { normalizeRuns, readEvidence, readVerifierTiers, type Reliability, type RunCounts } from './evidence';
import { readBenches, type BenchSummary } from './bench';
import { isReferenceSkill } from './reference';
import type { Contributor } from './rep';
import { readActionPrompts, type ActionPrompts } from './prompts';
import { readCleanDemos } from './clean-demos';
import { normalizeBeforeAfter, summarizeBeforeAfter, type BeforeAfterMetrics, type BeforeAfterSummary } from './before-after';

export interface Fingerprint {
	os: string; os_version?: string; hardware?: string; app_package?: string; app_version?: string;
	screen_wxh?: string; density?: string | number; locale?: string; theme?: string;
}

export interface VersionEntry {
	action_states?: Record<string, ActionState>;
	state_probes?: Record<string, unknown>;
	tag: string | null; commit: string; fingerprint: Fingerprint; actions: string[];
	data_access: string[]; tos_risk?: string | null; has_python: boolean; files: Record<string, string>; size_bytes: number;
}

export interface IndexRecord {
	version: string; tag: string | null; commit: string; git_tree: string;
	sha256: string; size: number; released_at: string; attestation: string | null;
}

export interface Quality {
	tier: Tier; score?: number; points?: number;
	categories?: Record<string, number>; freshness_multiplier?: number; provisional_until?: string | null;
	signals: {
		readme: boolean; soft_md: boolean; demo: boolean; bench: boolean; tests_pass: boolean | null;
		fingerprints_verified: number; last_verified: string | null;
		/** Passing runs by other accounts, one per device fingerprint (registry builder). */
		independent_runs?: number;
		independent_device_classes?: number;
		/** Honest-signals registry (trust lane): raw counts per evidence class. Optional until it lands. */
		maintainer_runs?: number; maintainer_runs_passed?: number;
		previous_version_runs?: number; previous_version_runs_passed?: number;
		emulator_runs?: number;
		/** Scoring v1.1: weighted validator units of the weakest action (`validators`) and every leaf (`validators_total`). */
		validators?: number; validators_total?: number;
	};
	/** NOT in contract v1. Optional run counts if build_registry starts emitting
	 *  them; until then every skill shows "not enough runs". */
	runs?: { device_grid?: DeviceGrid; passed: number; total: number; passed_90d?: number; total_90d?: number;
		self?: { passed: number; total: number }; independent?: { passed: number; total: number };
		/** Honest-signals registry: maintainer-signed replays and runs on earlier versions, raw counts. */
		maintainer?: { passed: number; total: number }; previous_version?: { passed: number; total: number };
		emulator?: number;
		/** Artifacts on disk the registry refused (unsigned, simulated, wrong-skill, bad-bench-block, bad-signature). */
		rejected?: { total: number; reasons?: Record<string, number> };
		/** Counted runs that carry a bench block (AndroidWorld cells). */
		bench?: number };
}

export interface RegistrySkill {
	author: string; slug: string; name: string; description: string; skill_class: 'hard' | 'soft';
	trust: Trust; latest: string; versions: Record<string, VersionEntry>; quality: Quality; updated_at: string;
	/** Lifecycle from skill.yaml `status:` (B1). Absent on older registries = active. */
	status?: SkillStatus;
	/** `stale_upstream`: the target app shipped a version outside the skill's fingerprint range (drift job). */
	flags?: { blocked?: boolean; stale_upstream?: boolean | { app_version?: string; seen_at?: string } };
	/** App icon, relative to the skill dir (e.g. `icon.webp`), or null. Absent on older registries. */
	icon?: string | null;
	/** Demo clip relative to the skill dir, or null. Absent on older registries. */
	demo?: { path: string; bytes?: number; type?: string } | null;
	/** One clip per action: {action: {path, bytes, type}}. Absent on older registries. */
	demos?: Record<string, { path: string; bytes?: number; type?: string }> | null;
	/** No-skill vs with-skill pair recording (demos/before-after.*): clip plus the measured numbers, or null.
	 *  Never run evidence. Absent on older registries. */
	before_after?: { clip: { path: string; bytes?: number; type?: string }; metrics?: unknown } | null;
	/** Lineage (v1.7 schema, optional): where a fork came from, what replaced this skill, why it was deprecated. */
	forked_from?: string | null;
	superseded_by?: string | null;
	deprecated_reason?: string | null;
}

/** A playable clip on the skill page. `action` is null for the skill-level overview clip. `clean` marks a clip
 *  from the clean-demo catalog (verified reset + HOME before launch); false is a recorded live-agent session
 *  clip shipped in the skill dir, shown with its own wording. */
export interface DemoClip { action: string | null; label: string; file: string; url: string; kind: DemoKind; clean: boolean }

/** The before / after pair clip with its numbers (null numbers when the json is absent or malformed). */
export interface BeforeAfter { file: string; url: string; kind: DemoKind; metrics: BeforeAfterMetrics | null; summary: BeforeAfterSummary | null }

export type DemoKind = 'webm' | 'mp4' | 'gif';
export const DEMO_MIME: Record<DemoKind, string> = { webm: 'video/webm', mp4: 'video/mp4', gif: 'image/gif' };

export type SkillStatus = 'active' | 'blocked' | 'deprecated' | 'draft';

export interface Registry {
	schema_version: number; generated_at: string; repo: string;
	authors: Record<string, { trust: Trust; github: string; skills: number }>;
	skills: Record<string, RegistrySkill>;
	rep_version?: string;
	contributors?: Record<string, Contributor>;
}

export interface Skill extends RegistrySkill {
	id: string;
	latestEntry: VersionEntry;
	index: IndexRecord[];            // newest first; empty if no index file
	versionList: { version: string; entry: VersionEntry; record?: IndexRecord }[];
	points: number;
	tierIndex: number;
	/** Registry still carries the pre-ladder C/B/A stub score; shown as Draft, 0 points. */
	legacyQuality: boolean;
	status: SkillStatus;
	blocked: boolean;                // hidden from default browse + leaderboard
	/** Benchmark reference skill (AndroidWorld scaffold): hidden from default browse, never ranked. */
	reference: boolean;
	staleUpstream: { app_version: string | null; seen_at: string | null } | null;
	lineage: { forkedFrom: string | null; supersededBy: string | null; deprecatedReason: string | null };
	/** Per-action evidence read from runs/ and verifications/ (display only). */
	reliability: Reliability;
	/** bench/androidworld.json summary (display only), or null. */
	bench: BenchSummary | null;
	benches: BenchSummary[];
	skillDir: string | null;         // on-disk skill dir, first docRoot that has it
	changelog: string | null;        // CHANGELOG.md in the skill dir, if any
	iconFile: string | null;         // absolute path of the validated icon on disk
	iconUrl: string | null;          // where the build emits it (pages/skills/icons/...)
	demo: { file: string; url: string; kind: DemoKind } | null;   // overview clip: first clean action clip, else the skill-level recording (demo.webm)
	demoClips: DemoClip[];           // tabs: overview (if any), then actions in skill order (clean clips first per action)
	actionPrompts: Record<string, ActionPrompts>;
	demoMissing: string[];           // actions without a clip ("no demo yet")
	beforeAfter: BeforeAfter | null; // no-skill vs with-skill pair (demos/before-after.*), or null
	/** total = every signed artifact; self = runs/ artifacts, independent = verifications/ artifacts
	 *  (quality.runs.self/independent; older registries fall back to signals.independent_runs). */
	/** Display counts from the registry or derived from the artifacts on disk. */
	runs: RunCounts;
	/** Sort tie-break only: Wilson LB with the 10/10 prior. Never shown as a rate. */
	rating: number | null;
	/** Confidence floor: raw 95% Wilson lower bound over counted runs, no prior; null without runs. */
	wilson: number | null;
	readme: string | null;
	soft: string | null;
	recent: boolean;                 // re-verified within RECENT_WINDOW_DAYS of generated_at
}

export interface Hub {
	source: 'live' | 'fixture';
	root: string;
	generatedAt: string;
	repo: string;
	skills: Skill[];
	authors: { handle: string; trust: Trust; github: string; skills: Skill[] }[];
	/** registry.json `contributors` (rep-v1); empty on a registry built before rep. */
	contributors: Contributor[];
	warnings: string[];
}

const SITE_ROOT = process.cwd();
const REPO_ROOT = resolve(SITE_ROOT, '..');

function readJson<T>(path: string): T {
	return JSON.parse(readFileSync(path, 'utf8')) as T;
}

function readText(path: string): string | null {
	return existsSync(path) ? readFileSync(path, 'utf8') : null;
}

function semverCmp(a: string, b: string): number {
	const pa = a.split(/[.-]/), pb = b.split(/[.-]/);
	for (let i = 0; i < 3; i++) {
		const d = (parseInt(pa[i] ?? '0', 10) || 0) - (parseInt(pb[i] ?? '0', 10) || 0);
		if (d) return d;
	}
	// a pre-release sorts below the release
	return (pa.length > 3 ? -1 : 0) - (pb.length > 3 ? -1 : 0);
}

/** Index files may be a bare array of records, `{versions: [...]}`, or a single
 *  record. The contract names the record fields but not the wrapper. */
function normalizeIndex(raw: unknown): IndexRecord[] {
	if (Array.isArray(raw)) return raw as IndexRecord[];
	if (raw && typeof raw === 'object') {
		const o = raw as Record<string, unknown>;
		if (Array.isArray(o.versions)) return o.versions as IndexRecord[];
		if (typeof o.version === 'string') return [o as unknown as IndexRecord];
	}
	return [];
}

function locate(): { source: 'live' | 'fixture'; root: string; registryPath: string; indexDir: string; docRoots: string[] } {
	const hubDir = process.env.HUB_DIR ? resolve(process.env.HUB_DIR) : join(REPO_ROOT, 'skillhub');
	const live = join(hubDir, 'registry.json');
	if (existsSync(live)) {
		return { source: 'live', root: hubDir, registryPath: live, indexDir: join(hubDir, 'registry', 'index'), docRoots: [hubDir] };
	}
	const fx = join(REPO_ROOT, 'tools', 'fixtures');
	return {
		source: 'fixture', root: fx, registryPath: join(fx, 'registry-sample.json'), indexDir: join(fx, 'registry', 'index'),
		// Fixture docs, then pre-migration official skills under gitd/skills/<slug>/.
		docRoots: [join(fx, 'skillhub'), hubDir],
	};
}

export { isReferenceSkill, REFERENCE_AUTHORS } from './reference';

function skillDirOf(docRoots: string[], author: string, slug: string): string | null {
	for (const r of docRoots) {
		const d = join(r, author, slug);
		if (existsSync(d)) return d;
	}
	return null;
}

function readDoc(docRoots: string[], author: string, slug: string, file: string): string | null {
	for (const r of docRoots) {
		const t = readText(join(r, author, slug, file));
		if (t != null) return t;
	}
	if (author === 'ghost') return readText(join(REPO_ROOT, 'gitd', 'skills', slug, file));
	return null;
}

export const ICON_MAX_BYTES = 16 * 1024;
export const FIXTURE_ICON = join(REPO_ROOT, 'tools', 'fixtures', 'icon.webp');

export function iconUrlFor(author: string, slug: string): string {
	return `/skills/icons/${author}/${slug}.webp`;
}

/** Resolve a path from the registry (relative to the skill dir) to a safe file
 *  on disk: relative, allowed extension, inside the skill dir, within maxBytes.
 *  Registry data is generated but still treated as untrusted input. */
function resolveSkillFile(roots: string[], author: string, slug: string, rel: unknown,
	opts: { what: string; exts: string[]; maxBytes: number; fallback: string }, warn: (m: string) => void): string | null {
	if (rel == null || rel === '') return null;
	const ext = typeof rel === 'string' ? rel.toLowerCase().split('.').pop() ?? '' : '';
	if (typeof rel !== 'string' || isAbsolute(rel) || !opts.exts.includes(ext) || normalize(rel).split(sep).includes('..')) {
		warn(`${author}/${slug}: ${opts.what} ${JSON.stringify(rel)} must be a relative ${opts.exts.map((e) => '.' + e).join('/')} path inside the skill dir; ${opts.fallback}`);
		return null;
	}
	for (const r of roots) {
		const dir = resolve(r, author, slug);
		const file = resolve(dir, rel);
		if (!file.startsWith(dir + sep) || !existsSync(file)) continue;
		const size = statSync(file).size;
		if (size > opts.maxBytes) {
			warn(`${author}/${slug}: ${opts.what} is ${size} bytes, over the ${opts.maxBytes} byte limit; ${opts.fallback}`);
			return null;
		}
		return file;
	}
	warn(`${author}/${slug}: ${opts.what} ${rel} not found; ${opts.fallback}`);
	return null;
}

export function resolveIcon(roots: string[], author: string, slug: string, rel: string | null | undefined, warn: (m: string) => void): string | null {
	return resolveSkillFile(roots, author, slug, rel, { what: 'icon', exts: ['webp'], maxBytes: ICON_MAX_BYTES, fallback: 'using the glyph' }, warn);
}

export const DEMO_MAX_BYTES = 3 * 1024 * 1024;
export const FIXTURE_DEMO = join(REPO_ROOT, 'tools', 'fixtures', 'demo.webm');

export function demoUrlFor(author: string, slug: string, kind: DemoKind): string {
	return `/skills/demos/${author}/${slug}.${kind}`;
}

export function actionDemoUrlFor(author: string, slug: string, action: string, kind: DemoKind): string {
	return `/skills/demos/${author}/${slug}/${action}.${kind}`;
}

export const BEFORE_AFTER_STEM = 'before-after';

export function beforeAfterUrlFor(author: string, slug: string, kind: DemoKind): string {
	return `/skills/demos/${author}/${slug}/${BEFORE_AFTER_STEM}.${kind}`;
}

/** The pair clip resolved like any demo (relative path inside the skill dir, allowed type, within the size limit);
 *  malformed numbers warn and drop to null so the clip still shows. */
export function resolveBeforeAfter(roots: string[], author: string, slug: string, raw: RegistrySkill['before_after'],
	warn: (m: string) => void): BeforeAfter | null {
	if (!raw || typeof raw !== 'object' || !raw.clip) return null;
	const r = resolveDemo(roots, author, slug, raw.clip, warn, (kind) => beforeAfterUrlFor(author, slug, kind), 'before/after clip');
	if (!r) return null;
	const metrics = normalizeBeforeAfter(raw.metrics, (m) => warn(`${author}/${slug}: before/after numbers ${m}; showing the pair without numbers`));
	return { ...r, metrics, summary: metrics ? summarizeBeforeAfter(metrics) : null };
}

export function resolveDemo(roots: string[], author: string, slug: string, demo: RegistrySkill['demo'], warn: (m: string) => void,
	urlFor: (kind: DemoKind) => string = (kind) => demoUrlFor(author, slug, kind), what = 'demo'): { file: string; url: string; kind: DemoKind } | null {
	if (!demo) return null;
	const file = resolveSkillFile(roots, author, slug, demo.path, { what, exts: Object.keys(DEMO_MIME), maxBytes: DEMO_MAX_BYTES, fallback: `skipping the ${what}` }, warn);
	if (!file) return null;
	const kind = file.toLowerCase().split('.').pop() as DemoKind;
	const declared = demo.type?.toLowerCase().replace(/^(video|image)\//, '');
	if (declared && declared !== kind) warn(`${author}/${slug}: ${what} type ${demo.type} does not match its .${kind} file; using the file extension`);
	return { file, url: urlFor(kind), kind };
}

const ACTION_NAME = /^[a-z][a-z0-9_-]{0,63}$/;

/** Per-action clips in the skill's action order. Unknown or unsafe action keys are skipped. */
export function resolveActionDemos(roots: string[], author: string, slug: string, actions: string[],
	demos: RegistrySkill['demos'], warn: (m: string) => void): DemoClip[] {
	if (!demos) return [];
	for (const key of Object.keys(demos)) {
		if (!ACTION_NAME.test(key) || !actions.includes(key)) warn(`${author}/${slug}: demo for unknown action ${JSON.stringify(key)}; skipping it`);
	}
	const out: DemoClip[] = [];
	for (const action of actions) {
		if (!ACTION_NAME.test(action) || !demos[action]) continue;
		const r = resolveDemo(roots, author, slug, demos[action], warn, (kind) => actionDemoUrlFor(author, slug, action, kind), `demo for ${action}`);
		if (r) out.push({ action, label: action, clean: false, ...r });
	}
	return out;
}

let cached: Hub | null = null;

export function loadHub(): Hub {
	if (cached) return cached;
	const loc = locate();
	const reg = readJson<Registry>(loc.registryPath);
	const warnings: string[] = [];
	if (reg.schema_version !== 2) warnings.push(`registry schema_version ${reg.schema_version}, site expects 2`);

	// Until the registry builder emits `icon`, every skill renders the fixture icon
	// so the image path is exercised end to end; a present-but-null icon gets the glyph.
	const iconsLanded = Object.values(reg.skills).some((e) => 'icon' in e);
	if (!iconsLanded) console.warn(`[skillhub] icons: registry has no icon field yet; using ${FIXTURE_ICON} for every skill`);
	const iconWarn = (m: string) => warnings.push(`icons: ${m}`);
	const cleanDemos = readCleanDemos(loc.root);

	const verifierTiers = readVerifierTiers(loc.root);
	const skills: Skill[] = [];
	for (const [id, s] of Object.entries(reg.skills)) {
		if (RESERVED_AUTHOR_NAMES.has(s.author)) {
			warnings.push(`skipped ${id}: author name "${s.author}" collides with a reserved /skills/ path`);
			continue;
		}
		const latestEntry = s.versions[s.latest];
		if (!latestEntry) {
			warnings.push(`skipped ${id}: latest ${s.latest} missing from versions`);
			continue;
		}
		const idxPath = join(loc.indexDir, `${s.author}.${s.slug}.json`);
		const index = existsSync(idxPath) ? normalizeIndex(readJson(idxPath)) : [];
		index.sort((a, b) => semverCmp(b.version, a.version));
		const versionList = Object.keys(s.versions)
			.sort((a, b) => semverCmp(b, a))
			.map((v) => ({ version: v, entry: s.versions[v], record: index.find((r) => r.version === v) }));

		const legacyQuality = !isLadderTier(s.quality?.tier);
		const q = { ...s.quality, tier: normalizeTier(s.quality?.tier) };
		const skillDir = skillDirOf(loc.docRoots, s.author, s.slug);
		const stale = s.flags?.stale_upstream;
		const reliability = readEvidence(skillDir ?? join(loc.root, s.author, s.slug), s.author, latestEntry.actions, { currentVersion: s.latest, verifierTiers });
		const runs = normalizeRuns(q as any, reliability);
		const enough = runs.total >= 20;
		const last = q.signals?.last_verified ?? null;
		skills.push({
			...s,
			quality: q,
			id,
			latestEntry,
			index,
			versionList,
			points: legacyQuality ? 0 : (q.points ?? q.score ?? 0),
			legacyQuality,
			status: s.status ?? (s.flags?.blocked ? 'blocked' : 'active'),
			blocked: s.flags?.blocked === true || s.status === 'blocked',
			reference: isReferenceSkill(s),
			staleUpstream: stale ? { app_version: typeof stale === 'object' ? stale.app_version ?? null : null, seen_at: typeof stale === 'object' ? stale.seen_at ?? null : null } : null,
			lineage: { forkedFrom: s.forked_from ?? null, supersededBy: s.superseded_by ?? null, deprecatedReason: s.deprecated_reason ?? null },
			reliability,
			...(() => { const benches = readBenches(skillDir, (m) => warnings.push(`bench: ${s.author}/${s.slug}: ${m}`)); return { benches, bench: benches.find((b) => b.suite === 'androidworld') ?? null }; })(),
			skillDir,
			actionPrompts: readActionPrompts(skillDir, id, latestEntry.actions),
			changelog: readDoc(loc.docRoots, s.author, s.slug, 'CHANGELOG.md'),
			...(() => {
				const file = iconsLanded ? resolveIcon(loc.docRoots, s.author, s.slug, s.icon, iconWarn) : FIXTURE_ICON;
				return { iconFile: file, iconUrl: file ? iconUrlFor(s.author, s.slug) : null };
			})(),
			...(() => {
				const actions = latestEntry.actions;
				const demoWarn = (m: string) => warnings.push(`demos: ${m}`);
				// Clean-reset clips from the catalog first (verified protocol); recorded session clips shipped in the
				// skill dir (registry `demos`) fill the actions that have no clean clip. Both are presentation only.
				const clean: DemoClip[] = actions.flatMap((action) => {
					const clip = cleanDemos.find((c) => c.skill === id && c.action === action);
					return clip ? [{ action, label: action, file: clip.file, kind: clip.kind, clean: true, url: actionDemoUrlFor(s.author, s.slug, action, clip.kind) }] : [];
				});
				const withClean = new Set(clean.map((c) => c.action));
				const recorded = resolveActionDemos(loc.docRoots, s.author, s.slug, actions, s.demos, demoWarn).filter((c) => !withClean.has(c.action));
				const perAction = actions.flatMap((a) => [...clean, ...recorded].filter((c) => c.action === a));
				const first = clean[0];
				// Overview: the first clean clip, else the skill-level recording (demo.webm|mp4|gif in the skill dir).
				// The registry's default clip may be an action clip (the loader prefers those), so look at the dir itself.
				const isActionClip = !!s.demo && Object.values(s.demos ?? {}).some((d) => d?.path === s.demo?.path);
				const overviewRel = s.demo && !isActionClip ? s.demo.path
					: (['demo.webm', 'demo.mp4', 'demo.gif'].find((n) => skillDir && existsSync(join(skillDir, n))) ?? null);
				const skillLevel = overviewRel ? resolveDemo(loc.docRoots, s.author, s.slug, { path: overviewRel }, demoWarn) : null;
				const demo = first ? { file: first.file, kind: first.kind, url: demoUrlFor(s.author, s.slug, first.kind) } : skillLevel;
				const withClip = new Set(perAction.map((c) => c.action));
				return {
					demo,
					demoClips: [...(demo ? [{ action: null, label: 'Overview', clean: !!first, ...demo }] : []), ...perAction],
					demoMissing: actions.filter((a) => !withClip.has(a)),
					beforeAfter: resolveBeforeAfter(loc.docRoots, s.author, s.slug, s.before_after, demoWarn),
				};
			})(),
			tierIndex: TIER_INDEX[q.tier] ?? 0,
			runs,
			rating: enough ? displayRating(runs.passed, runs.total) : null,
			wilson: runs.total > 0 ? wilsonLower(runs.passed, runs.total) : null,
			readme: readDoc(loc.docRoots, s.author, s.slug, 'README.md'),
			soft: readDoc(loc.docRoots, s.author, s.slug, 'SOFT.md'),
			recent: last != null && daysBetween(last, reg.generated_at) <= RECENT_WINDOW_DAYS,
		});
	}
	skills.sort((a, b) => b.tierIndex - a.tierIndex || b.points - a.points || a.id.localeCompare(b.id));

	const byAuthor = new Map<string, Skill[]>();
	for (const s of skills) byAuthor.set(s.author, [...(byAuthor.get(s.author) ?? []), s]);
	const authors = [...byAuthor.entries()].map(([handle, list]) => ({
		handle,
		trust: reg.authors[handle]?.trust ?? list[0].trust,
		github: reg.authors[handle]?.github ?? handle,
		skills: list,
	})).sort((a, b) => a.handle.localeCompare(b.handle));

	const contributors = Object.values(reg.contributors ?? {}).filter((c) => {
		if (!RESERVED_AUTHOR_NAMES.has(c.login)) return true;
		warnings.push(`skipped contributor ${c.login}: name collides with a reserved /skills/ path`);
		return false;
	});
	for (const w of warnings) console.warn(`[skillhub] ${w}`);
	cached = { source: loc.source, root: loc.root, generatedAt: reg.generated_at, repo: reg.repo, skills, authors, contributors, warnings };
	return cached;
}

export { runSplit, passedOverRuns } from './evidence';

export function formatBytes(n: number): string {
	if (n < 1024) return `${n} B`;
	if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
	return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDate(iso: string | null | undefined): string {
	if (!iso) return 'never';
	return new Date(iso).toISOString().slice(0, 10);
}
