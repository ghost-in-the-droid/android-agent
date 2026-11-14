import { test, expect } from '@playwright/test';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { resolve, join } from 'node:path';
import yaml from 'js-yaml';
import { showcasePages, showcaseViewports } from '../../scripts/showcase-pages.mjs';
// Independent reference sums from the published files, never from the page helper or fixtures.
const root = resolve('../skillhub');
const manifest = yaml.load(readFileSync(join(root, 'showcase.yml'), 'utf8')) as { skills: { ref: string; task_ids?: string[]; task?: string }[] };
const refs = [...new Set(manifest.skills.map((s) => s.ref))];
const tasksByRef = Object.fromEntries(refs.map((ref) => {
 const dir = join(root, ref, 'bench');
 const tasks = existsSync(dir) ? readdirSync(dir).filter((p) => p.endsWith('.json')).flatMap((p) => {
  const b = JSON.parse(readFileSync(join(dir, p), 'utf8'));
  return ['androidworld', 'ghost-native'].includes(b.suite) ? b.tasks : [];
 }) : [];
 return [ref, tasks];
}));
const skillActions = Object.fromEntries(refs.map((ref) => [ref, (yaml.load(readFileSync(join(root, ref, 'skill.yaml'), 'utf8')) as any).actions]));
const declarations = manifest.skills.flatMap(({ ref, task_ids, task }) => (task_ids ?? (task ? [task] : [])).map((id) => ({ ref, task: id })));
const selected = [...new Map(declarations.map((s) => [s.ref + '/' + s.task, s])).values()].flatMap(({ ref, task }) => tasksByRef[ref].filter((t: any) => t.task_id === task));
const sum = (arm: string) => selected.reduce((s, t) => {
 const r = t.arms[arm];
 return r && r.valid !== false ? { passed: s.passed + r.passed, total: s.total + r.total } : s;
}, { passed: 0, total: 0 });
const before = sum('before'), after = sum('after_mcp');
for (const viewport of showcaseViewports) for (const colorScheme of ['light', 'dark'] as const) {
 test.describe(`${viewport.width} ${colorScheme}`, () => {
  test.use({ viewport, colorScheme, deviceScaleFactor: 1 });
  for (const path of showcasePages) test(`${path} has no console errors or horizontal overflow`, async ({ page }) => {
   const errors: string[] = [];
   page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
   page.on('pageerror', (e) => errors.push(e.message));
   const response = await page.goto(path, { waitUntil: 'networkidle' });
   expect(response?.ok()).toBe(true);
   await page.evaluate(() => document.fonts.ready);
   await expect(page.locator('h1').first()).toBeVisible();
   expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
   if (path === '/skills/showcase/') {
    await expect(page.locator('html')).toHaveAttribute('data-hub-theme', 'dark');
    if (colorScheme === 'light') {
     await page.locator('[data-theme-toggle]').click();
     await expect(page.locator('html')).toHaveAttribute('data-hub-theme', 'light');
    }
    if (viewport.width === 1280) expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(1350);
    await expect(page.locator('[data-showcase-skill]')).toHaveCount(refs.length);
    await expect(page.locator('[data-pooled-pass]')).toHaveText(`${before.passed}/${before.total} → ${after.passed}/${after.total}`);
    await expect(page.locator('.showcase-footnote')).toContainText('Every failure is counted (intention-to-treat).');
    await expect(page.locator('.showcase-kpis > .panel')).toHaveCount(3);
    for (const ref of refs) await expect(page.locator(`[data-showcase-skill="${ref}"] [data-action]`)).toHaveCount(tasksByRef[ref].length);
    await expect(page.locator('.showcase-details[open]')).toHaveCount(0);
    await expect(page.locator('.action-columns > span')).toHaveText(['Skill', 'Action', 'Tokens saved', 'Before / with']);
    const disclosure = page.locator('.showcase-details').first();
    const row = disclosure.locator('summary');
    const panel = disclosure.locator('.index-details');
    await expect(row.locator('a, button, input, select, textarea, [tabindex]')).toHaveCount(0);
    await expect(row).toHaveAttribute('aria-controls', await panel.getAttribute('id') as string);
    await expect(row).toHaveAttribute('aria-expanded', 'false');
    await expect(panel).toBeHidden();
    // Click a content cell, not a separate Explore button.
    await row.locator('.index-action').click();
    await expect(row).toHaveAttribute('aria-expanded', 'true');
    await expect(panel.locator('[data-prompt-text]').first()).toBeVisible();
    await expect(panel.locator('[data-copy-prompt]').first()).toBeVisible();
    await expect(panel.getByRole('link', { name: 'Full evidence, failures and traces →' })).toBeVisible();
    await row.press('Enter');
    await expect(row).toHaveAttribute('aria-expanded', 'false');
    await expect(panel).toBeHidden();
    // Reach the native summary through sequential keyboard navigation.
    await row.press('Shift+Tab');
    await page.keyboard.press('Tab');
    await expect(row).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(row).toHaveAttribute('aria-expanded', 'true');
    await expect(panel.locator('[data-prompt-text]').first()).toBeVisible();
    await row.press('Space');
    await expect(row).toHaveAttribute('aria-expanded', 'false');
    await row.press('Space');
    await expect(row).toHaveAttribute('aria-expanded', 'true');
    await expect(panel.locator('[data-prompt-text]').first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await row.click();
    await expect(row).toHaveAttribute('aria-expanded', 'false');
    for (const ref of refs) for (const task of tasksByRef[ref]) {
     const action = skillActions[ref].find((a: any) => a.name === task.action);
     await expect(page.locator(`[data-showcase-skill="${ref}"] [data-action="${task.action}"] [data-prompt-text]`).first()).toHaveText(action.ref_prompt.trim());
    }
    await expect(page.locator('[data-chart="tokens"] svg')).toHaveCount(selected.length);
    await page.getByRole('tab', { name: 'UI actions', exact: true }).click();
    await expect(page.locator('[data-chart="actions"]')).toBeVisible();
    await expect(page.locator('[data-chart="tokens"]')).toBeHidden();
    await page.getByRole('tab', { name: 'UI actions', exact: true }).press('ArrowRight');
    await expect(page.locator('[data-chart="time"]')).toBeVisible();
    await page.getByRole('tab', { name: 'Time', exact: true }).press('Home');
    await expect(page.locator('[data-chart="tokens"]')).toBeVisible();
    await page.locator('.showcase-details').evaluateAll((details) => details.forEach((d) => d.setAttribute('open', '')));
   }
   if (path !== '/skills/showcase/') {
    await page.locator('#tab-actions').click();
    const ref = path.split('/').filter(Boolean).slice(1).join('/');
    for (const action of skillActions[ref]) {
     const prompts = [action.ref_prompt.trim(), ...new Set((action.test_case?.ref_prompt_variants ?? []).filter((v: any) => typeof v === 'string').map((v: string) => v.trim()).filter((v: string) => v && v !== action.ref_prompt.trim()))].slice(0, 4);
     await expect(page.locator(`[data-skill-action="${action.name}"] [data-prompt-text]`)).toHaveText(prompts);
    }
   }
   await page.locator('[data-benchmark-details]').evaluateAll((details) => details.forEach((d) => d.setAttribute('open', '')));
   await page.locator('[data-bench-episodes]').evaluateAll((details) => details.forEach((d) => d.setAttribute('open', '')));
   expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
   expect(errors).toEqual([]);
  });
 });
}


test('sample prompt copy writes the exact text and reports clipboard failure', async ({ page, context }) => {
 await context.grantPermissions(['clipboard-read', 'clipboard-write']);
 await page.goto('/skills/showcase/');
 await page.locator('.showcase-details').first().locator('summary').click();
 const block = page.locator('[data-action-prompts]').first();
 const expected = await block.locator('[data-prompt-text]').first().textContent();
 await block.locator('[data-copy-prompt]').first().click();
 await expect(block.getByRole('status')).toHaveText('Prompt copied.');
 expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(expected);
 await page.evaluate(() => Object.defineProperty(navigator.clipboard, 'writeText', { value: () => Promise.reject(new Error('denied')) }));
 await block.locator('[data-copy-prompt]').first().click();
 await expect(block.getByRole('status')).toHaveText('Select the prompt text to copy it.');
});

test('sample prompts remain readable without JavaScript', async ({ browser }) => {
 const context = await browser.newContext({ javaScriptEnabled: false });
 const page = await context.newPage();
 try {
  for (const path of ['/skills/ghost/calculator/', '/skills/showcase/']) {
   await page.goto(new URL(path, process.env.BASE_URL ?? 'http://localhost:4321').href);
   if (path === '/skills/showcase/') await page.locator('.showcase-details').first().locator('summary').click();
   await expect(page.locator('[data-prompt-text]').first()).toBeVisible();
   await expect(page.locator('[data-copy-prompt]').first()).toBeHidden();
  }
 } finally { await context.close(); }
});


test('showcase explicit theme persists and reduced motion disables bar animation', async ({ page }) => {
 await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
 await page.goto('/skills/showcase/');
 await expect(page.locator('html')).toHaveAttribute('data-hub-theme', 'dark');
 expect(await page.locator('.bar-after').first().evaluate((bar) => getComputedStyle(bar).animationName)).toBe('none');
 await page.locator('[data-theme-toggle]').click();
 await page.reload();
 await expect(page.locator('html')).toHaveAttribute('data-hub-theme', 'light');
 await page.locator('[data-theme-toggle]').click();
 await expect(page.locator('html')).toHaveAttribute('data-hub-theme', 'dark');
 await page.locator('.benchmark-row').first().focus();
 await expect(page.locator('.benchmark-row').first().getByRole('tooltip')).toContainText('Wilson');
});

test('skill QR promises an install page and keeps its HTTPS link', async ({ page }) => {
 await page.goto('/skills/androidworld/pro-expense/');
 const qr = page.locator('.panel.qr');
 await expect(qr.getByText("Scan to open this skill's install page on your phone.", { exact: false })).toBeVisible();
 await expect(qr.locator('p')).toHaveText(/^Scan to open this skill's install page on your phone\.ghost/);
 await expect(qr.locator('a')).toHaveCount(1);
 await expect(qr.locator('a')).toHaveAttribute('href', /^https:\/\//);
 await expect(qr.locator('[role="img"] svg')).toHaveCount(1);
 await expect(page.locator('[data-device-coverage]')).toContainText('No independent device runs yet.');
});
