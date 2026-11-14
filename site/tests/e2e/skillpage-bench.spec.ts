import { test, expect } from '@playwright/test';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
const root = resolve('../skillhub');
const registry = JSON.parse(readFileSync(join(root, 'registry.json'), 'utf8'));
const refs = ['ghost/calculator', 'androidworld/pro-expense'];
const benchTasks = (ref: string) => readdirSync(join(root, ref, 'bench')).filter((name) => name.endsWith('.json')).flatMap((name) => JSON.parse(readFileSync(join(root, ref, 'bench', name), 'utf8')).tasks).filter((t: any) => t.arms.before && t.arms.after_mcp);
const median = (values: number[]) => {
 const sorted = [...values].sort((a, b) => a - b), middle = Math.floor(sorted.length / 2);
 return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};
const expectedSaving = (tasks: any[], field: 'tokens' | 'ui_actions') => tasks.reduce((sum, t) => {
 const values = t.episodes.filter((e: any) => e.arm === 'before' && e.valid !== false).flatMap((before: any) => {
  const after = t.episodes.find((e: any) => e.arm === 'after_mcp' && e.seed === before.seed && e.valid !== false);
  const b = field === 'tokens' ? before.tokens : before.ui_actions?.total;
  const a = field === 'tokens' ? after?.tokens : after?.ui_actions?.total;
  return typeof a === 'number' && typeof b === 'number' ? [b - a] : [];
 });
 return sum + (values.length ? median(values) : 0);
}, 0).toLocaleString('en-US', { maximumFractionDigits: 1 });
for (const width of [1280, 390]) for (const colorScheme of ['dark', 'light'] as const) {
 test.describe(`skill pages ${width} ${colorScheme}`, () => {
  test.use({ viewport: { width, height: 900 }, colorScheme });
  for (const ref of refs) test(`${ref}: compact truthful summary and collapsed padded details`, async ({ page }) => {
   const errors: string[] = [];
   page.on('pageerror', (e) => errors.push(e.message));
   page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
   await page.goto(`/skills/${ref}/`, { waitUntil: 'networkidle' });
   const tasks = benchTasks(ref), summary = page.locator('[data-skill-bench-summary]');
   await expect(summary).toBeVisible();
   expect(await page.locator('.page-head').evaluate((head) => head.nextElementSibling?.matches('[data-skill-bench-summary]'))).toBe(true);
   await expect(summary.locator('.benchmark-row')).toHaveCount(tasks.length);
   await expect(summary.locator('.bench-kpis > div')).toHaveCount(3);
   await expect(summary.locator('[data-skill-token-saving]')).toHaveText(expectedSaving(tasks, 'tokens'));
   await expect(summary.locator('[data-skill-action-saving]')).toHaveText(expectedSaving(tasks, 'ui_actions'));
   const count = (arm: string) => `${tasks.reduce((n: number, t: any) => n + t.arms[arm].passed, 0)}/${tasks.reduce((n: number, t: any) => n + t.arms[arm].total, 0)}`;
   await expect(summary.locator('[data-skill-pass]')).toHaveText(`${count('before')} → ${count('after_mcp')}`);
   await expect(summary).toContainText('maintainer-run, not independent');
   if (ref === 'ghost/calculator') await expect(summary.locator('[data-unbenched]')).toHaveText('3 more actions not benchmarked yet');
   else await expect(summary.locator('[data-unbenched]')).toHaveCount(0);
   const details = page.locator('[data-benchmark-details]');
   expect(await details.getAttribute('open')).toBeNull();
   expect(await page.locator('.skill-grid').evaluate((grid) => grid.nextElementSibling?.matches('[data-benchmark-details]'))).toBe(true);
   await expect(details.locator('[data-bench]').first()).toBeHidden();
   await summary.locator('[data-open-bench]').click();
   await expect(details).toHaveAttribute('open', '');
   await expect(details.locator('[data-bench]').first()).toBeVisible();
   expect(await details.locator('[data-bench]').first().evaluate((card) => parseFloat(getComputedStyle(card).paddingLeft))).toBeGreaterThanOrEqual(12);
   await expect(details.locator('[data-bench-paired]').first()).toContainText(/Agent \+ skill vs agent alone|Skill replay vs agent alone/);
   for (const key of ['after_mcp_vs_before', 'after_replay_vs_before']) await expect(details.locator('[data-bench-paired]').first()).not.toContainText(key);
   expect(await details.locator('td.num').first().evaluate((td) => getComputedStyle(td).textAlign)).toBe('right');
   const sha = details.locator('[data-short-sha] code').first();
   expect((await sha.textContent())?.length).toBeLessThanOrEqual(8);
   if (ref === 'androidworld/pro-expense') await expect(details.getByRole('heading', { name: 'pre-fix (supply-chain finding)' }).first()).toBeVisible();
   await details.locator('[data-bench-episodes]').evaluateAll((items) => items.forEach((d) => d.setAttribute('open', '')));
   expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
   expect(errors).toEqual([]);
  });
  test('browse scores come from the registry and sort numerically', async ({ page }) => {
   const errors: string[] = [];
   page.on('pageerror', (e) => errors.push(e.message));
   page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
   await page.goto('/skills/', { waitUntil: 'networkidle' });
   await expect(page.locator('th.c-score')).toBeVisible();
   for (const row of await page.locator('#rows > tr').all()) {
    const ref = (await row.getAttribute('data-name'))!;
    const score = registry.skills[ref].quality.points ?? registry.skills[ref].quality.score;
    await expect(row.locator('[data-skill-score]')).toHaveText(`${score}/100`);
   }
   const visible = page.locator('#rows > tr:visible');
   await expect(visible.first().locator('[data-skill-score]')).toBeVisible();
   for (const order of ['score', 'score-asc']) {
    await page.locator('th button[data-sort="score"]').click();
    const scores = await visible.evaluateAll((rows) => rows.map((r) => Number((r as HTMLElement).dataset.score)));
    expect(scores).toEqual([...scores].sort((a, b) => order === 'score' ? b - a : a - b));
   }
   expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
   expect(errors).toEqual([]);
  });
 });
}
test('short SHA copies full provenance and exposes full text when clipboard is denied', async ({ page, context }) => {
 await context.grantPermissions(['clipboard-read', 'clipboard-write']);
 await page.goto('/skills/androidworld/pro-expense/#benchmarks');
 const details = page.locator('[data-benchmark-details]');
 await expect(details).toHaveAttribute('open', '');
 const block = details.locator('[data-short-sha]').first();
 const button = block.locator('button'), full = (await button.getAttribute('data-copy-sha'))!;
 await button.click();
 expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(full);
 await expect(block.getByRole('status')).toHaveText('Copied.');
 await page.evaluate(() => Object.defineProperty(navigator.clipboard, 'writeText', { value: () => Promise.reject(new Error('denied')) }));
 await button.click();
 await expect(block.locator('code')).toHaveText(full);
 await expect(block.getByRole('status')).toHaveText('Select the full value to copy it.');
});


test('unbenchmarked skill shows one quiet coverage line without empty charts', async ({ page }) => {
 await page.goto('/skills/ghost/camera/');
 await expect(page.locator('[data-unbenched]')).toHaveCount(1);
 await expect(page.locator('[data-unbenched]')).toContainText('actions not benchmarked yet');
 await expect(page.locator('[data-skill-bench-summary]')).toHaveCount(0);
});
