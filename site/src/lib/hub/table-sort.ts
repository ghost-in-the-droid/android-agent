// Column-header sorting for the /skills/ browse table. Pure functions so the toggle is unit-testable.
export type SortKey = 'name' | 'actions' | 'score' | 'runs' | 'savings';
export type SortDir = 'asc' | 'desc';
export interface SortState { key: SortKey | null; dir: SortDir }

export const NUMERIC_KEYS: SortKey[] = ['actions', 'score', 'runs', 'savings'];

/** First click on a column: numbers start high-to-low, names A-Z. Second click flips. */
export function nextSort(state: SortState, key: SortKey): SortState {
	if (state.key === key) return { key, dir: state.dir === 'asc' ? 'desc' : 'asc' };
	return { key, dir: key === 'name' ? 'asc' : 'desc' };
}

export function ariaSort(state: SortState, key: SortKey): 'ascending' | 'descending' | 'none' {
	return state.key !== key ? 'none' : state.dir === 'asc' ? 'ascending' : 'descending';
}

export interface SortRow { name: string; order: number; actions: number; score: number; runs: number; savings?: number }

function base(a: SortRow, b: SortRow, key: SortKey): number {
	switch (key) {
		case 'name': return a.name.localeCompare(b.name);
		case 'actions': return a.actions - b.actions;
		case 'score': return a.score - b.score;
		case 'runs': return a.runs - b.runs;
		case 'savings': return (a.savings ?? 0) - (b.savings ?? 0);
	}
}

/** Stable comparator: ties fall back to name, then registry order. With no active column it is registry order. */
export function compareRows(state: SortState, a: SortRow, b: SortRow): number {
	if (!state.key) return a.order - b.order;
	const d = base(a, b, state.key) * (state.dir === 'asc' ? 1 : -1);
	return d || a.name.localeCompare(b.name) || a.order - b.order;
}
