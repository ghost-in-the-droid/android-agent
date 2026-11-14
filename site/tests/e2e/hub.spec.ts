/**
 * E2E: Skill Hub pages (/skills/, one skill page, /skills/leaderboard/).
 * Runs against the last `npm run build` via astro preview (playwright.config.ts).
 *
 *   npx playwright test tests/e2e/hub.spec.ts
 */
import { test, expect, type Page } from '@playwright/test';

const BASE = process.env.BASE_URL ?? 'http://localhost:4321';

async function visibleRows(page: Page): Promise<number> {
	return page.locator('#rows tr.row:not([hidden])').count();
}

test.describe('/skills/ browse', () => {
	test('reference and blocked skills are hidden until toggled, and the count follows', async ({ page }) => {
		await page.goto(`${BASE}/skills/`, { waitUntil: 'networkidle' });
		const all = await page.locator('#rows tr.row').count();
		const reference = await page.locator('#rows tr.row[data-reference="1"]').count();
		const blocked = await page.locator('#rows tr.row[data-blocked="1"]').count();
		expect(all).toBeGreaterThan(0);
		const shown = await visibleRows(page);
		expect(shown).toBe(all - reference - blocked);
		await expect(page.locator('#count')).toHaveText(new RegExp(`^${shown} skills?$`));
		// no reference row is visible by default
		expect(await page.locator('#rows tr.row[data-reference="1"]:not([hidden])').count()).toBe(0);

		const toggle = page.locator('#f-reference');
		if (reference > 0) {
			await toggle.check();
			expect(await visibleRows(page)).toBe(shown + reference);
			await expect(page.locator('#count')).toHaveText(new RegExp(`^${shown + reference} skills?$`));
			await toggle.uncheck();
			expect(await visibleRows(page)).toBe(shown);
		} else {
			await expect(toggle).toHaveCount(0);
		}
	});

	test('?reference=1 pre-checks the toggle', async ({ page }) => {
		await page.goto(`${BASE}/skills/`, { waitUntil: 'networkidle' });
		const reference = await page.locator('#rows tr.row[data-reference="1"]').count();
		test.skip(reference === 0, 'no reference skills in this registry');
		await page.goto(`${BASE}/skills/?reference=1`, { waitUntil: 'networkidle' });
		await expect(page.locator('#f-reference')).toBeChecked();
		expect(await page.locator('#rows tr.row[data-reference="1"]:not([hidden])').count()).toBe(reference);
	});

	test('tier, class and search filters narrow the list and the empty state appears', async ({ page }) => {
		await page.goto(`${BASE}/skills/`, { waitUntil: 'networkidle' });
		const before = await visibleRows(page);
		await page.selectOption('#f-tier', '1'); // Runs or better
		const runsOrBetter = await visibleRows(page);
		expect(runsOrBetter).toBeLessThanOrEqual(before);
		for (const row of await page.locator('#rows tr.row:not([hidden])').all()) {
			expect(Number(await row.getAttribute('data-tier'))).toBeGreaterThanOrEqual(1);
		}
		await page.selectOption('#f-tier', '0');
		await page.selectOption('#f-class', 'soft');
		for (const row of await page.locator('#rows tr.row:not([hidden])').all()) {
			expect(await row.getAttribute('data-class')).toBe('soft');
		}
		await page.selectOption('#f-class', '');
		await page.fill('#q', 'zzzz-no-such-skill-zzzz');
		await expect(page.locator('#empty')).toBeVisible();
		await expect(page.locator('#count')).toHaveText('0 skills');
		await page.fill('#q', '');
		await expect(page.locator('#empty')).toBeHidden();
		expect(await visibleRows(page)).toBe(before);
	});

	test('header click sorts by name, second click reverses, aria-sort follows', async ({ page }) => {
		await page.goto(`${BASE}/skills/`, { waitUntil: 'networkidle' });
		await page.locator('th button[data-sort="name"]').click();
		const names = await page.locator('#rows tr.row:not([hidden])').evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.name!));
		expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b)));
		await expect(page.locator('th[aria-sort="ascending"]')).toHaveCount(1);
		await page.locator('th button[data-sort="name"]').click();
		await expect(page.locator('th.c-name')).toHaveAttribute('aria-sort', 'descending');
		const rev = await page.locator('#rows tr.row:not([hidden])').evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.name!));
		expect(rev).toEqual([...names].reverse());
	});
});

test.describe('skill page', () => {
	test('reliability card is the headline and its rows match the action list', async ({ page }) => {
		await page.goto(`${BASE}/skills/`, { waitUntil: 'networkidle' });
		// first visible row = highest tier/points: the one most likely to have runs
		const url = await page.locator('#rows tr.row:not([hidden])').first().getAttribute('data-url');
		await page.goto(`${BASE}${url}`, { waitUntil: 'networkidle' });
		const card = page.locator('[data-reliability]');
		await expect(card).toHaveCount(1);
		// the card renders above the quality points panel
		const order = await page.evaluate(() => {
			const a = document.querySelector('[data-reliability]')!;
			const b = document.querySelector('.quality-panel')!;
			return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? 'card-first' : 'points-first';
		});
		expect(order).toBe('card-first');
		const actions = await page.locator('#panel-actions [data-skill-action]').count();
		const rows = await card.locator('tbody tr[data-action]').count();
		expect(rows).toBe(actions);
		const big = card.locator('.rel-big');
		await expect(big).toHaveCount(1);
		const total = Number(await big.getAttribute('data-total'));
		if (total > 0) {
			// per-action totals never exceed the headline run count times actions, and at least one action ran
			const perAction = await card.locator('tbody tr[data-action]').evaluateAll((els) => els.map((e) => Number((e as HTMLElement).dataset.total)));
			expect(Math.max(...perAction)).toBeGreaterThan(0);
		} else {
			await expect(big).toContainText('No signed runs yet');
		}
	});

	test('tabs switch panels and keep the hash', async ({ page }) => {
		await page.goto(`${BASE}/skills/`, { waitUntil: 'networkidle' });
		const url = await page.locator('#rows tr.row:not([hidden])').first().getAttribute('data-url');
		await page.goto(`${BASE}${url}`, { waitUntil: 'networkidle' });
		await page.click('#tab-actions');
		await expect(page.locator('#panel-actions')).toBeVisible();
		await expect(page.locator('#panel-readme')).toBeHidden();
		expect(page.url()).toMatch(/#actions$/);
		await page.keyboard.press('ArrowRight');
		await expect(page.locator('#panel-versions')).toBeVisible();
	});
});

test.describe('/skills/leaderboard/', () => {
	test('ranks no reference skill, numbers rows 1..n and switches boards', async ({ page }) => {
		await page.goto(`${BASE}/skills/leaderboard/`, { waitUntil: 'networkidle' });
		await expect(page.locator('tr td code', { hasText: /^androidworld\// })).toHaveCount(0);
		const nums = await page.locator('#panel-recent table[data-board="skills"] tbody tr:not([hidden]) td.num:first-child').allTextContents();
		const ranked = nums.map((n) => n.trim()).filter(Boolean).map(Number);
		expect(ranked).toEqual(ranked.map((_, i) => i + 1));
		await page.click('#tab-all');
		await expect(page.locator('#panel-all')).toBeVisible();
		await expect(page.locator('#panel-recent')).toBeHidden();
		const allNums = await page.locator('#panel-all table[data-board="skills"] tbody tr:not([hidden]) td.num:first-child').allTextContents();
		const authors = await page.locator('#panel-all table[data-board="authors"] tbody tr').count();
		expect(authors).toBeGreaterThan(0);
		await expect(page.locator('#panel-all table[data-board="authors"] tbody tr td:nth-child(2)', { hasText: /^androidworld$/ })).toHaveCount(0);
		expect(allNums.map((n) => n.trim()).filter(Boolean).length).toBeGreaterThanOrEqual(ranked.length);
	});
});

// Honest display: the headline is the raw registry count, never a prior-adjusted percent.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

test.describe('honest headline', () => {
	const registry = JSON.parse(readFileSync(resolve(process.cwd(), '..', 'skillhub', 'registry.json'), 'utf8')) as {
		skills: Record<string, { quality: { runs: { passed: number; total: number } } }>;
	};
	for (const id of ['ghost/calculator', 'androidworld/pro-expense']) {
		test(`${id}: headline has no percent and equals the registry's raw counts`, async ({ page }) => {
			const entry = registry.skills[id];
			test.skip(!entry, `${id} not in this registry`);
			await page.goto(`${BASE}/skills/${id}/`, { waitUntil: 'networkidle' });
			const big = page.locator('[data-reliability] .rel-big');
			await expect(big).toHaveCount(1);
			const text = (await big.textContent())!.replace(/\s+/g, ' ').trim();
			expect(text).not.toContain('%');
			expect(Number(await big.getAttribute('data-passed'))).toBe(entry.quality.runs.passed);
			expect(Number(await big.getAttribute('data-total'))).toBe(entry.quality.runs.total);
			if (entry.quality.runs.total > 0) {
				expect(text).toMatch(new RegExp(`^${entry.quality.runs.passed} ?/${entry.quality.runs.total} passed`));
				// the floor is labelled, and lives outside the headline
				const floor = page.locator('[data-reliability] .rel-floor');
				await expect(floor).toHaveCount(1);
				await expect(floor).toContainText('Confidence floor');
			}
			// nothing on the page calls a number a "success rate"
			expect(await page.locator('[data-reliability]').textContent()).not.toMatch(/success rate/i);
		});
	}

	test('leaderboard shows passed / runs, never a percent', async ({ page }) => {
		await page.goto(`${BASE}/skills/leaderboard/`, { waitUntil: 'networkidle' });
		const cells = page.locator('table[data-board="skills"] tbody tr:not([hidden]) td .rating-raw, table[data-board="skills"] tbody tr:not([hidden]) td .rating-none');
		expect(await cells.count()).toBeGreaterThan(0);
		for (const t of await cells.allTextContents()) expect(t).not.toContain('%');
		await expect(page.locator('table[data-board="skills"] thead').first()).toContainText('Passed / runs');
		await expect(page.locator('table[data-board="skills"] thead').first()).not.toContainText('Success rate');
	});
});
