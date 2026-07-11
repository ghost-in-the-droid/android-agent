/**
 * E2E: /showcase + landing hero — modal a11y, reduced-motion, network deps.
 *
 * Ported from ghost-neutral-review's audit script (all 10 assertions passed
 * headless against the f26b2e1 build). Run against `astro preview`:
 *
 *   npx playwright test tests/e2e/showcase.spec.ts
 *
 * with playwright.config webServer = { command: 'npm run preview', port: 4321 }
 * or set BASE_URL.
 */
import { test, expect, type Page } from '@playwright/test';

const BASE = process.env.BASE_URL ?? 'http://localhost:4321';

test.describe('showcase page', () => {
	test('tiles render and modal is keyboard-accessible', async ({ page }) => {
		await page.goto(`${BASE}/showcase/`, { waitUntil: 'networkidle' });

		const tiles = page.locator('[data-demo-tile]');
		expect(await tiles.count()).toBeGreaterThan(0);

		// open via keyboard
		await tiles.first().focus();
		await page.keyboard.press('Enter');
		const dialog = page.locator('dialog[open]');
		await expect(dialog).toHaveCount(1);

		// showModal() moves focus into the dialog asynchronously — wait for it
		// to land before exercising the trap, or the first Tab races the shift.
		await expect
			.poll(() => page.evaluate(() => !!document.activeElement?.closest('dialog[open]')))
			.toBe(true);

		// native focus trap: Tab never escapes the open dialog
		for (let i = 0; i < 8; i++) {
			await page.keyboard.press('Tab');
			expect(
				await page.evaluate(() => !!document.activeElement?.closest('dialog[open]')),
			).toBe(true);
		}

		// Esc closes and focus returns to the invoking tile
		await page.keyboard.press('Escape');
		await expect(dialog).toHaveCount(0);
		expect(
			await page.evaluate(() => document.activeElement?.hasAttribute('data-demo-tile')),
		).toBe(true);
	});

	test('backdrop click closes modal and pauses video', async ({ page }) => {
		await page.goto(`${BASE}/showcase/`, { waitUntil: 'networkidle' });
		await page.locator('[data-demo-tile]').first().click();
		await expect(page.locator('dialog[open]')).toHaveCount(1);

		await page.mouse.click(8, 8); // backdrop
		await expect(page.locator('dialog[open]')).toHaveCount(0);
		// The close-time pause resolves a tick after the play() promise rejects,
		// so poll rather than reading paused synchronously.
		await expect
			.poll(() =>
				page.evaluate(() =>
					[...document.querySelectorAll<HTMLVideoElement>('dialog video')].every((v) => v.paused),
				),
			)
			.toBe(true);
	});

	test('sizzle autoplays only without prefers-reduced-motion', async ({ browser }) => {
		for (const reducedMotion of ['no-preference', 'reduce'] as const) {
			const ctx = await browser.newContext({ reducedMotion });
			const page = await ctx.newPage();
			await page.goto(`${BASE}/showcase/`, { waitUntil: 'networkidle' });
			const state = await page
				.locator('[data-sizzle-video]')
				.evaluate((v: HTMLVideoElement) => ({ autoplay: v.autoplay, paused: v.paused }));
			if (reducedMotion === 'reduce') {
				expect(state.autoplay).toBe(false);
				expect(state.paused).toBe(true);
			} else {
				expect(state.autoplay).toBe(true);
			}
			await ctx.close();
		}
	});

	test('no unexpected external network requests', async ({ page }) => {
		// Google Fonts is the known pre-existing exception (tracked for self-host
		// post-tag). Anything else external is a regression.
		const ALLOWED = [/^https:\/\/fonts\.googleapis\.com\//, /^https:\/\/fonts\.gstatic\.com\//];
		const violations: string[] = [];
		page.on('request', (r) => {
			const url = r.url();
			if (url.startsWith(BASE) || url.startsWith('data:')) return;
			if (!ALLOWED.some((re) => re.test(url))) violations.push(url);
		});
		await page.goto(`${BASE}/showcase/`, { waitUntil: 'networkidle' });
		await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
		expect(violations).toEqual([]);
	});

	test('landing page hero swap: sizzle + 3 featured cards', async ({ page }) => {
		await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
		await expect(page.locator('[data-sizzle-video]')).toHaveCount(1);
		await expect(page.locator('.featured-card')).toHaveCount(3);
	});
});
