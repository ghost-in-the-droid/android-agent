export interface ActionState {
	requires_state?: string[];
	provides_state?: string[];
	clears_state?: string[];
	idempotent?: boolean;
}

/** Display declarations, never infer authentication or award evidence points. */
export function stateBadges(value?: ActionState): string[] {
	return (['requires_state', 'provides_state', 'clears_state'] as const).flatMap((key) => {
		const prefix = { requires_state: 'Requires', provides_state: 'Sets', clears_state: 'Clears' }[key];
		return (Array.isArray(value?.[key]) ? value[key] : [])
			.filter((state) => typeof state === 'string' && /^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/.test(state))
			.map((state) => `${prefix}: ${state.replaceAll('_', ' ')}`);
	});
}
