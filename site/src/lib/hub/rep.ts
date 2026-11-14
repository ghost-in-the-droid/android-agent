// Contributor reputation. Point values and badge rules come from ONE file,
// `skillhub/scoring/rep-v1.json` (owned by tools/rep.py); every contributor
// number comes from registry.json `contributors`. The site adds labels only.

import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

export interface RepTable {
	version: string;
	published: { per_skill: string; excluded_statuses?: string[]; excluded_authors?: string[] };
	verified: { independent_run: number; new_device_class: number; new_bench_model: number };
	maintained: { per_skill: number };
	badges: { id: string; label: string; rule: string; description: string }[];
	rules: string[];
}

export interface Contributor {
	login: string;
	github: string;
	trust: string | null;
	maintainers: string[];
	rep: number;
	breakdown: { published: number; verified: number; maintained: number };
	published: { skill: string; points: number; tier: string | null; status: string | null }[];
	verified: { skill: string; points: number; runs: number; new_device_classes: number; new_bench_models: number }[];
	maintained: { skill: string; points: number; runs: number; new_bench_models: number }[];
	stats: Record<string, number>;
	badges: string[];
}

export const EMPTY_REP_TABLE: RepTable = {
	version: 'none',
	published: { per_skill: 'quality_points' },
	verified: { independent_run: 0, new_device_class: 0, new_bench_model: 0 },
	maintained: { per_skill: 0 },
	badges: [],
	rules: [],
};

export function loadRepTable(): RepTable {
	const repo = resolve(process.cwd(), '..');
	const hub = process.env.HUB_DIR ? resolve(process.env.HUB_DIR) : join(repo, 'skillhub');
	const path = join(hub, 'scoring', 'rep-v1.json');
	if (!existsSync(path)) {
		console.warn(`[skillhub] rep: ${path} not found; contributor rep is hidden`);
		return EMPTY_REP_TABLE;
	}
	return JSON.parse(readFileSync(path, 'utf8')) as RepTable;
}

export const REP = loadRepTable();

/** GitHub login syntax; anything else never becomes an avatar URL or a profile link. */
const LOGIN = /^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$/;
export const isGithubLogin = (s: string | null | undefined): s is string => typeof s === 'string' && LOGIN.test(s);
export const avatarUrl = (login: string, size = 128) => (isGithubLogin(login) ? `https://github.com/${login}.png?size=${size}` : null);

/** Highest rep first; ties by verified, then login, so the order is stable. */
export function rankContributors(list: Contributor[]): Contributor[] {
	return [...list].sort((a, b) => b.rep - a.rep || b.breakdown.verified - a.breakdown.verified || a.login.localeCompare(b.login));
}

export function badgesOf(c: Pick<Contributor, 'badges'>, table: RepTable = REP) {
	const byId = new Map(table.badges.map((b) => [b.id, b]));
	return c.badges.map((id) => byId.get(id) ?? { id, label: id, rule: '', description: '' });
}

/** Human-readable point rules generated from the table (scoring page). */
export function repPointRules(table: RepTable = REP): { source: string; points: string }[] {
	const v = table.verified;
	return [
		{ source: 'Published: each skill in your namespace', points: 'its current quality points (0 to 100)' },
		{ source: 'Verified: independent passing run of someone else\'s skill', points: `${v.independent_run} per counted run` },
		{ source: 'Device pioneer: first independent pass on a new device class', points: `+${v.new_device_class}` },
		{ source: 'New bench model: first run with an agent model the author never benched', points: `+${v.new_bench_model}` },
		{ source: 'Maintained: re-verified someone else\'s skill with a maintainer or platform key', points: `${table.maintained.per_skill} per skill` },
		{ source: 'Downloads, likes, stars', points: '0' },
	];
}
