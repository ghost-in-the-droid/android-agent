import { test, expect } from '@playwright/test';
import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const registry = JSON.parse(readFileSync(resolve('..', 'skillhub/registry.json'), 'utf8'));
for (const width of [390, 768, 1280]) {
 test(`compact browse at ${width}px: five columns, one-line rows, token savings`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.goto('/skills/', { waitUntil: 'networkidle' });
  await expect(page.locator('.browse-table th')).toHaveText(['#', 'Skill', 'Description', 'Token savings', 'Score']);
  for (const select of await page.locator('.toolbar select').all()) {
   const box = (await select.boundingBox())!;
   expect(box.width).toBeGreaterThan(80);
   expect(box.height).toBeGreaterThanOrEqual(39);
  }
  const rows = page.locator('#rows tr:not([hidden])');
  expect(await rows.count()).toBeGreaterThan(10);
  for (const row of (await rows.all()).slice(0, 12)) {
   const id = (await row.getAttribute('data-name'))!;
   expect(registry.skills[id]).toBeTruthy();
   const box = (await row.boundingBox())!;
   expect(box.height).toBeGreaterThanOrEqual(55);
   expect(box.height).toBeLessThanOrEqual(57);
   await expect(row.locator('.pkg, .chip, .ladder, .score-bar, .status, .c-ver, .c-tier')).toHaveCount(0);
   await expect(row.locator('.skill-identity')).toBeVisible();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.locator('th button[data-sort="savings"]').click();
  const counts = await rows.evaluateAll((els) => els.map((e) => Number((e as HTMLElement).dataset.savings)));
  expect(counts).toEqual([...counts].sort((a, b) => b - a));
  await expect(page.locator('th.c-savings')).toHaveAttribute('aria-sort', 'descending');
  await expect(rows.first().locator('[data-rank]')).toHaveText('1');
  await page.locator('th button[data-sort="savings"]').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('th.c-savings')).toHaveAttribute('aria-sort', 'ascending');
  await page.fill('#q', 'clock');
  await expect(page.locator('#rows tr:not([hidden])').first().locator('[data-rank]')).toHaveText('1');
  await page.goto('/skills/', { waitUntil: 'networkidle' });
  const shots = process.env.HUB_SCREENSHOT_DIR;
  if (shots && width !== 768) {
   mkdirSync(shots, { recursive: true });
   await page.screenshot({ path: resolve(shots, width === 1280 ? 'browse-desktop.png' : 'browse-phone.png') });
  }
 });
}
