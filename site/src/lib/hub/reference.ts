// Benchmark reference skills: generated from AndroidWorld tasks under the
// `androidworld` author namespace, no authored steps yet. Hidden from the
// default browse, never ranked. Dependency-free so the unit tests can import it
// under plain Node.
export const REFERENCE_AUTHORS = new Set(['androidworld']);

export interface ReferenceProbe { author: string }

export function isReferenceSkill(s: ReferenceProbe): boolean {
	return REFERENCE_AUTHORS.has(s.author);
}
