// Build-time reader for signed run evidence: `runs/*.json` (self-runs) and
// `verifications/*.json` (independent runs) inside a skill dir. The registry
// carries only skill-level totals; the reliability card needs per-action rows,
// the fingerprints tested and the app versions seen, so the site reads the
// artifacts themselves. Display only: nothing here awards points.
//
// Artifact shape (gitd/skills/engine/evidence.py, schema_version 1):
//   kind, skill, version, fingerprint{os, os_version, hardware, app_package, app_version},
//   fingerprint_hash, app_version, device_class, timestamp, finished_at, success,
//   actions[{name, success, duration_ms, error_kind, steps[]}], device_backend, simulation, signature.
// Verifications add `verifier` (a GitHub login). Simulated runs (`simulation:
// true` or a non-device backend) are counted separately and never as evidence.

import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

export interface RunArtifact {
	kind?: string;
	skill?: string;
	version?: string;
	fingerprint?: Record<string, unknown>;
	fingerprint_hash?: string;
	app_version?: string;
	device_class?: string;
	timestamp?: string;
	finished_at?: string;
	success?: boolean;
	actions?: { name?: string; success?: boolean; duration_ms?: number; error_kind?: string | null }[];
	device_backend?: string;
	simulation?: boolean;
	signature?: unknown;
	verifier?: string | null;
	/** Optional bench block (AndroidWorld before/after); display only. */
	bench?: { suite?: string; task_id?: string; arm?: string; seed?: number | string } | null;
}

export interface ActionReliability {
	action: string;
	passed: number;
	total: number;
	self: { passed: number; total: number };
	independent: { passed: number; total: number };
	/** ISO timestamp of the newest counted run, or null when the action has none. */
	lastRun: string | null;
	/** Newest run's app version first, de-duplicated. */
	appVersions: string[];
	/** Human error kinds seen on failed runs, most frequent first. */
	errorKinds: string[];
	/** Median duration of passing runs in ms, or null. */
	medianMs: number | null;
}

export interface FingerprintSeen {
	hash: string;
	deviceClass: string;
	appVersions: string[];
	runs: number;
	passed: number;
	independent: boolean;
	/** Signed by a maintainer-held key (verifier-keys.yml tier maintainer/platform). */
	maintainer: boolean;
	/** Device model looks like an emulator image (sdk_gphone, goldfish, ranchu, generic). */
	emulator: boolean;
	lastRun: string | null;
}

export interface EvidenceClass { passed: number; total: number }

/** How a verifier principal is trusted, from skillhub/verifier-keys.yml. */
export type VerifierTier = 'maintainer' | 'platform' | 'community';

export interface Reliability {
	passed: number;
	total: number;
	self: EvidenceClass;
	independent: EvidenceClass;
	/** Verifications signed by a maintainer-held key: reproducibility evidence, not independent. */
	maintainer: EvidenceClass;
	/** Counted runs recorded on a skill version other than the one on disk. */
	previousVersion: EvidenceClass;
	/** Counted runs on the version on disk. */
	currentVersion: EvidenceClass;
	/** Counted runs whose device looks like an emulator image. */
	emulator: number;
	/** Distinct fingerprints among independent (non-maintainer) verifications. */
	independentDevices: number;
	lastRun: string | null;
	appVersions: string[];
	fingerprints: FingerprintSeen[];
	actions: ActionReliability[];
	/** Artifacts ignored: simulated or non-device runs, unsigned, unparseable. */
	excluded: { simulated: number; unsigned: number; invalid: number };
	verifiers: string[];
	/** Verifier principal -> tier, for the ones seen. */
	verifierTiers: Record<string, VerifierTier>;
}

const EMPTY_SPLIT = () => ({ passed: 0, total: 0 });

const EMULATOR_RE = /sdk_gphone|goldfish|ranchu|emulator|generic_x86|generic_arm|android_x86/i;

/** Does this artifact's device look like an emulator image? Display heuristic on
 *  the recorded hardware string; the registry's own `emulator_runs` wins when present. */
export function looksLikeEmulator(a: RunArtifact): boolean {
	const hw = String(a.fingerprint?.hardware ?? '');
	return EMULATOR_RE.test(hw) || EMULATOR_RE.test(String(a.device_class ?? ''));
}

/** Parse the `principals:` block of skillhub/verifier-keys.yml (two-space YAML, no library):
 *  `{principal: tier}`. Missing file or unparseable block = {} (every verifier counts as community). */
export function parseVerifierTiers(text: string): Record<string, VerifierTier> {
	const out: Record<string, VerifierTier> = {};
	let inPrincipals = false;
	let current: string | null = null;
	for (const raw of text.split(/\r?\n/)) {
		const line = raw.replace(/\s+#.*$/, '').trimEnd();
		if (!line.trim() || line.trim().startsWith('#')) continue;
		const indent = line.length - line.trimStart().length;
		if (indent === 0) { inPrincipals = /^principals:\s*$/.test(line); current = null; continue; }
		if (!inPrincipals) continue;
		if (indent === 2 && /^[A-Za-z0-9_.-]+:\s*$/.test(line.trim())) { current = line.trim().slice(0, -1); out[current] = 'community'; continue; }
		const m = /^tier:\s*([A-Za-z]+)\s*$/.exec(line.trim());
		if (current && indent === 4 && m) {
			const t = m[1].toLowerCase();
			out[current] = t === 'maintainer' || t === 'platform' ? t : 'community';
		}
	}
	return out;
}

export function readVerifierTiers(hubRoot: string): Record<string, VerifierTier> {
	const file = join(hubRoot, 'verifier-keys.yml');
	if (!existsSync(file)) return {};
	try { return parseVerifierTiers(readFileSync(file, 'utf8')); } catch { return {}; }
}

function runTime(a: RunArtifact): string | null {
	const t = a.finished_at ?? a.timestamp ?? null;
	return t && !Number.isNaN(Date.parse(t)) ? new Date(t).toISOString() : null;
}

function newest(a: string | null, b: string | null): string | null {
	if (!a) return b;
	if (!b) return a;
	return Date.parse(b) > Date.parse(a) ? b : a;
}

function median(xs: number[]): number | null {
	if (xs.length === 0) return null;
	const s = [...xs].sort((x, y) => x - y);
	const m = s.length >> 1;
	return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** Is this artifact real device evidence? Mirrors the registry builder's rule
 *  (simulated or non-device runs never score) so the card and the score agree. */
export function isEvidence(a: RunArtifact): 'ok' | 'simulated' | 'unsigned' {
	if (!a.signature) return 'unsigned';
	if (a.simulation === true) return 'simulated';
	if (a.device_backend && a.device_backend !== 'device') return 'simulated';
	return 'ok';
}

/** Pure summary of parsed artifacts. `independent` marks verifications by someone
 *  other than the author; the caller decides that (file location + verifier login). */
export function summarizeEvidence(
	artifacts: { artifact: RunArtifact; independent: boolean }[],
	actions: string[],
	invalid = 0,
	opts: { currentVersion?: string | null; verifierTiers?: Record<string, VerifierTier> } = {},
): Reliability {
	const tiers = opts.verifierTiers ?? {};
	const tierOf = (v: unknown): VerifierTier => tiers[String(v ?? '')] ?? 'community';
	const out: Reliability = {
		passed: 0, total: 0, self: EMPTY_SPLIT(), independent: EMPTY_SPLIT(), maintainer: EMPTY_SPLIT(),
		previousVersion: EMPTY_SPLIT(), currentVersion: EMPTY_SPLIT(), emulator: 0, independentDevices: 0,
		lastRun: null, appVersions: [],
		fingerprints: [], actions: [], excluded: { simulated: 0, unsigned: 0, invalid }, verifiers: [], verifierTiers: {},
	};
	const independentFps = new Set<string>();
	const byAction = new Map<string, ActionReliability & { durations: number[]; errors: Map<string, number>; versions: Map<string, string> }>();
	for (const a of actions) {
		byAction.set(a, { action: a, passed: 0, total: 0, self: EMPTY_SPLIT(), independent: EMPTY_SPLIT(), lastRun: null, appVersions: [], errorKinds: [], medianMs: null, durations: [], errors: new Map(), versions: new Map() });
	}
	const fps = new Map<string, FingerprintSeen & { versions: Map<string, string> }>();
	const tiersSeen: Record<string, VerifierTier> = {};
	const skillVersions = new Map<string, string>(); // app_version -> newest run time
	const verifiers = new Set<string>();

	const sorted = [...artifacts].sort((x, y) => (Date.parse(runTime(y.artifact) ?? '0') || 0) - (Date.parse(runTime(x.artifact) ?? '0') || 0));
	for (const { artifact, independent: byOther } of sorted) {
		const gate = isEvidence(artifact);
		if (gate !== 'ok') { out.excluded[gate]++; continue; }
		const when = runTime(artifact);
		const ok = artifact.success === true;
		const appVersion = String(artifact.app_version ?? artifact.fingerprint?.app_version ?? '').trim();
		// A verification by a maintainer-held key is reproducibility evidence, not independent.
		const tier = byOther ? tierOf(artifact.verifier) : 'community';
		const maintainer = byOther && tier !== 'community';
		const independent = byOther && !maintainer;
		const emulator = looksLikeEmulator(artifact);
		out.total++; if (ok) out.passed++;
		const split = independent ? out.independent : maintainer ? out.maintainer : out.self;
		split.total++; if (ok) split.passed++;
		const ver = opts.currentVersion == null ? null : String(artifact.version ?? '') === String(opts.currentVersion);
		if (ver !== null) { const v = ver ? out.currentVersion : out.previousVersion; v.total++; if (ok) v.passed++; }
		if (emulator) out.emulator++;
		out.lastRun = newest(out.lastRun, when);
		if (appVersion && !skillVersions.has(appVersion)) skillVersions.set(appVersion, when ?? '');
		if (byOther && artifact.verifier) { verifiers.add(String(artifact.verifier)); tiersSeen[String(artifact.verifier)] = tier; }

		const hash = String(artifact.fingerprint_hash ?? '');
		if (independent && hash) independentFps.add(hash);
		if (hash) {
			const fp = fps.get(hash) ?? { hash, deviceClass: String(artifact.device_class ?? deviceClassOf(artifact.fingerprint)), appVersions: [], runs: 0, passed: 0, independent: false, maintainer: false, emulator: false, lastRun: null, versions: new Map() };
			fp.runs++; if (ok) fp.passed++;
			fp.independent = fp.independent || independent;
			fp.maintainer = fp.maintainer || maintainer;
			fp.emulator = fp.emulator || emulator;
			fp.lastRun = newest(fp.lastRun, when);
			if (appVersion && !fp.versions.has(appVersion)) fp.versions.set(appVersion, when ?? '');
			fps.set(hash, fp);
		}

		for (const act of artifact.actions ?? []) {
			const name = String(act?.name ?? '');
			const row = byAction.get(name);
			if (!row) continue; // unknown action name: not in this version's action list
			const pass = act.success === true;
			row.total++; if (pass) row.passed++;
			const s = independent ? row.independent : row.self;
			s.total++; if (pass) s.passed++;
			row.lastRun = newest(row.lastRun, when);
			if (appVersion && !row.versions.has(appVersion)) row.versions.set(appVersion, when ?? '');
			if (pass && typeof act.duration_ms === 'number' && Number.isFinite(act.duration_ms)) row.durations.push(act.duration_ms);
			if (!pass) {
				const kind = String(act.error_kind ?? 'failed');
				row.errors.set(kind, (row.errors.get(kind) ?? 0) + 1);
			}
		}
	}

	out.appVersions = [...skillVersions.keys()];
	out.fingerprints = [...fps.values()]
		.map(({ versions, ...fp }) => ({ ...fp, appVersions: [...versions.keys()] }))
		.sort((a, b) => Number(b.independent) - Number(a.independent) || b.runs - a.runs || a.deviceClass.localeCompare(b.deviceClass));
	out.actions = [...byAction.values()].map(({ durations, errors, versions, ...row }) => ({
		...row,
		appVersions: [...versions.keys()],
		errorKinds: [...errors.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k),
		medianMs: median(durations),
	}));
	out.verifiers = [...verifiers].sort();
	out.verifierTiers = tiersSeen;
	out.independentDevices = independentFps.size;
	return out;
}

function deviceClassOf(fp: Record<string, unknown> | undefined): string {
	if (!fp) return 'unknown device';
	const hw = fp.hardware ? String(fp.hardware) : '';
	const os = fp.os_version ? String(fp.os_version) : '';
	return [hw, os].filter(Boolean).join('/') || 'unknown device';
}

/** Read every artifact under `<skillDir>/runs` and `<skillDir>/verifications`.
 *  A verification counts as independent only when its verifier is not the author
 *  (case-insensitive), the same rule the registry builder applies. */
export function readEvidence(skillDir: string, author: string, actions: string[],
	opts: { currentVersion?: string | null; verifierTiers?: Record<string, VerifierTier> } = {}): Reliability {
	const parsed: { artifact: RunArtifact; independent: boolean }[] = [];
	let invalid = 0;
	for (const sub of ['runs', 'verifications'] as const) {
		const dir = join(skillDir, sub);
		if (!existsSync(dir)) continue;
		for (const name of readdirSync(dir).sort()) {
			if (!name.endsWith('.json')) continue;
			let data: RunArtifact;
			try {
				data = JSON.parse(readFileSync(join(dir, name), 'utf8')) as RunArtifact;
			} catch {
				invalid++;
				continue;
			}
			if (!data || typeof data !== 'object') { invalid++; continue; }
			if (sub === 'verifications') {
				const stem = name.slice(0, -5).split('-');
				data.verifier = data.verifier ?? (stem.length >= 3 ? stem[0] : null);
				data.fingerprint_hash = data.fingerprint_hash ?? (stem.length >= 3 ? stem[1] : undefined);
			} else if (!data.fingerprint_hash) {
				data.fingerprint_hash = name.slice(0, -5).split('-')[0];
			}
			const independent = sub === 'verifications' && !!data.verifier && String(data.verifier).toLowerCase() !== author.toLowerCase();
			parsed.push({ artifact: data, independent });
		}
	}
	return summarizeEvidence(parsed, actions, invalid, opts);
}

/** "3 days ago" / "today" / "never" for the card. */
export function ageLabel(iso: string | null, nowIso: string): string {
	if (!iso) return 'never';
	const days = Math.floor((Date.parse(nowIso) - Date.parse(iso)) / 86_400_000);
	if (days <= 0) return 'today';
	if (days === 1) return 'yesterday';
	if (days < 60) return `${days} days ago`;
	const months = Math.floor(days / 30);
	return `${months} months ago`;
}

/** One verifier row on the card (contract: quality.runs.verifiers[]). */
export interface VerifierRow { principal: string; tier: VerifierTier; class: 'self' | 'maintainer' | 'ci' | 'independent'; label: string; passed: number; total: number }

/** Normalised run counts the pages print (registry contract: tools/build_registry.py,
 *  with the artifact-derived fallback for registries that predate it). */
export interface RunCounts {
	passed: number; total: number; passed90: number; total90: number;
	currentVersion: string | null;
	classes: { self: EvidenceClass; maintainer: EvidenceClass; ci: EvidenceClass; independent: EvidenceClass };
	previousVersions: EvidenceClass;
	emulator: { passed: number; total: number; unknown: number };
	independentDevices: number;
	verifiers: VerifierRow[];
	rejected: { total: number; reasons: Record<string, number> };
	bench: number;
	/** Where the class split came from. */
	classesSource: 'registry' | 'artifacts';
	/** Kept for older call sites: self.total and independent.total. */
	self: number; independent: number;
}

const ZERO = (): EvidenceClass => ({ passed: 0, total: 0 });
const cls = (c: unknown, fallback: EvidenceClass = ZERO()): EvidenceClass => {
	if (!c || typeof c !== 'object') return fallback;
	const o = c as Record<string, unknown>;
	return typeof o.total === 'number' ? { passed: typeof o.passed === 'number' ? o.passed : 0, total: o.total } : fallback;
};

/** Build the display counts from a registry `quality` block, falling back to the
 *  artifacts read from disk when the registry predates the honest-signals contract. */
export function normalizeRuns(quality: { runs?: Record<string, unknown> | null; signals?: Record<string, unknown> | null } | undefined, fromDisk: Reliability): RunCounts {
	const r = (quality?.runs ?? {}) as Record<string, any>;
	const sig = (quality?.signals ?? {}) as Record<string, any>;
	const num = (v: unknown, d = 0): number => (typeof v === 'number' && Number.isFinite(v) ? v : d);
	const fromRegistry = !!(r.maintainer || r.previous_versions || r.ci || Array.isArray(r.verifiers) || typeof sig.runs_maintainer_total === 'number');
	const total = num(r.total);
	const rejectedRaw = r.rejected;
	const rejected = {
		total: typeof rejectedRaw === 'number' ? rejectedRaw : num(rejectedRaw?.total),
		reasons: Object.fromEntries(Object.entries(rejectedRaw && typeof rejectedRaw === 'object' ? rejectedRaw.reasons ?? {} : {}).filter(([, n]) => typeof n === 'number' && n > 0)) as Record<string, number>,
	};
	if (fromRegistry) {
		const emu = r.emulator && typeof r.emulator === 'object' ? r.emulator : {};
		const verifiers: VerifierRow[] = (Array.isArray(r.verifiers) ? r.verifiers : []).flatMap((v: any) => {
			if (!v || typeof v !== 'object' || typeof v.principal !== 'string') return [];
			const tier: VerifierTier = v.tier === 'maintainer' || v.tier === 'platform' ? v.tier : 'community';
			const klass = ['self', 'maintainer', 'ci', 'independent'].includes(v.class) ? v.class : tier === 'community' ? 'independent' : 'maintainer';
			return [{ principal: v.principal, tier, class: klass, label: typeof v.label === 'string' && v.label ? v.label : v.principal, passed: num(v.passed), total: num(v.total) }];
		});
		const classes = {
			self: cls(r.self, { passed: num(sig.runs_self_passed), total: num(sig.runs_self_total) }),
			maintainer: cls(r.maintainer, { passed: num(sig.runs_maintainer_passed), total: num(sig.runs_maintainer_total) }),
			ci: cls(r.ci, { passed: num(sig.runs_ci_passed), total: num(sig.runs_ci_total) }),
			independent: cls(r.independent, { passed: num(sig.runs_independent_passed), total: num(sig.runs_independent_total) }),
		};
		return {
			passed: num(r.passed), total, passed90: num(r.passed_90d), total90: num(r.total_90d),
			currentVersion: typeof r.current_version === 'string' ? r.current_version : null,
			classes,
			previousVersions: cls(r.previous_versions, { passed: num(sig.runs_previous_passed), total: num(sig.runs_previous_total) }),
			emulator: { passed: num(emu.passed, num(sig.runs_emulator_passed)), total: num(emu.total, num(sig.runs_emulator_total)), unknown: num(emu.unknown, num(sig.runs_emulator_unknown)) },
			independentDevices: num(r.independent_devices, num(sig.independent_devices, num(sig.independent_device_classes))),
			verifiers, rejected, bench: num(r.bench),
			classesSource: 'registry',
			self: classes.self.total, independent: classes.independent.total,
		};
	}
	// Pre-contract registry: totals from the registry, the class split from the artifacts on disk
	// (verifier tier from verifier-keys.yml, version from the artifact, emulator from the device model).
	const independentLegacy = r.independent ? num(r.independent.total) : Math.min(total, Math.max(0, num(sig.independent_runs)));
	const verifiers: VerifierRow[] = fromDisk.verifiers.map((principal) => {
		const tier = fromDisk.verifierTiers[principal] ?? 'community';
		return { principal, tier, class: tier === 'community' ? 'independent' : 'maintainer', label: principal, passed: 0, total: 0 };
	});
	return {
		passed: num(r.passed), total, passed90: num(r.passed_90d), total90: num(r.total_90d),
		currentVersion: null,
		classes: { self: fromDisk.self, maintainer: fromDisk.maintainer, ci: ZERO(), independent: fromDisk.independent },
		previousVersions: fromDisk.previousVersion,
		emulator: { passed: 0, total: fromDisk.emulator, unknown: 0 },
		independentDevices: typeof sig.independent_device_classes === 'number' ? sig.independent_device_classes : fromDisk.independentDevices,
		verifiers, rejected, bench: num(r.bench),
		classesSource: 'artifacts',
		self: fromDisk.self.total || (total - independentLegacy), independent: fromDisk.independent.total || independentLegacy,
	};
}

/** "32 runs: 32 self-recorded, 3 maintainer-signed replays, 0 independent (3 on an emulator)." */
export function runSplit(runs: Pick<RunCounts, 'passed' | 'total' | 'classes' | 'emulator'>): string {
	const c = runs.classes;
	const parts = [`${c.self.total} self-recorded`];
	if (c.maintainer.total > 0) parts.push(`${c.maintainer.total} maintainer-signed ${c.maintainer.total === 1 ? 'replay' : 'replays'}`);
	if (c.ci.total > 0) parts.push(`${c.ci.total} CI-reproduced`);
	parts.push(`${c.independent.total} independent`);
	const emu = runs.emulator.total;
	return `${runs.total} ${runs.total === 1 ? 'run' : 'runs'}: ${parts.join(', ')}${emu > 0 ? ` (${emu} on an emulator)` : ''}.`;
}

/** "32/32" for a cell; "no runs" when nothing counted. */
export function passedOverRuns(runs: { passed: number; total: number }): string {
	return runs.total === 0 ? 'no runs' : `${runs.passed}/${runs.total}`;
}
