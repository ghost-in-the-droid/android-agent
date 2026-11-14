// Editorial media only. Deliberately outside registry demos, runs and scoring.
export interface HumanAssistedDemo {
 url: string;
 captions: string;
 poster: string;
 date: string;
 device: string;
}
const demos: Readonly<Record<string, HumanAssistedDemo>> = {};
export const humanAssistedDemoFor = (skillId: string): HumanAssistedDemo | undefined => demos[skillId];
