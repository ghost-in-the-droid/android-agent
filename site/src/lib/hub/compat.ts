// Release-wide compatibility matrix: skills x device setups, from each skill's signed run artifacts.
import type { Skill } from './registry';

const DEVICE_NAMES: Record<string, string> = {
	'samsung/sm-a037f': 'Galaxy A03s',
	'samsung/sm-a156b': 'Galaxy A15 5G',
	'google/sdk_gphone64_x86_64': 'Emulator',
	'asus/asus_i002d': 'ROG Phone 5',
};

/** Native screen of known phone models (WxH @ dpi); emulators vary, so none is claimed. */
const DEVICE_SCREENS: Record<string, string> = {
	'samsung/sm-a037f': '720×1600 · 300 dpi',
	'samsung/sm-a156b': '1080×2340 · 450 dpi',
};

export interface CompatColumn { key: string; device: string; android: string; screen: string | null; skills: number; runs: number; passed: number }
export interface CompatCell { passed: number; total: number }
export interface CompatRow { skill: Skill; cells: Record<string, CompatCell> }
export interface CompatMatrix { columns: CompatColumn[]; rows: CompatRow[] }

/** "samsung/SM-A037F/13" -> { key, device: "Galaxy A03s", android: "13" } */
export function parseDeviceClass(deviceClass: string): { key: string; device: string; android: string; screen: string | null } {
	const parts = deviceClass.split('/');
	const android = parts.length > 2 ? parts[parts.length - 1] : '?';
	const hw = parts.slice(0, 2).join('/');
	return { key: `${hw.toLowerCase()}/${android}`, device: DEVICE_NAMES[hw.toLowerCase()] ?? hw, android, screen: DEVICE_SCREENS[hw.toLowerCase()] ?? null };
}

export function buildCompat(skills: Skill[]): CompatMatrix {
	const cols = new Map<string, CompatColumn>();
	const rows: CompatRow[] = [];
	for (const skill of skills) {
		const cells: Record<string, CompatCell> = {};
		for (const fp of skill.reliability?.fingerprints ?? []) {
			if (!fp.deviceClass || fp.runs === 0) continue;
			const d = parseDeviceClass(fp.deviceClass);
			const cell = (cells[d.key] ??= { passed: 0, total: 0 });
			cell.passed += fp.passed; cell.total += fp.runs;
			const col = cols.get(d.key) ?? { key: d.key, device: d.device, android: d.android, screen: d.screen, skills: 0, runs: 0, passed: 0 };
			col.runs += fp.runs; col.passed += fp.passed;
			cols.set(d.key, col);
		}
		for (const key of Object.keys(cells)) cols.get(key)!.skills += 1;
		if (Object.keys(cells).length) rows.push({ skill, cells });
	}
	const emu = (c: CompatColumn) => (c.device === 'Emulator' ? 1 : 0);
	const columns = [...cols.values()].sort((a, b) => emu(a) - emu(b) || b.skills - a.skills || a.key.localeCompare(b.key));
	rows.sort((a, b) => a.skill.id.localeCompare(b.skill.id));
	return { columns, rows };
}
