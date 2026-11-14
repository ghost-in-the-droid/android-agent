import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'node:url';

test('Ghost Skill header link offers both agent guides', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Ghost Skill', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Ghost Skill', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Ghost — use the phone' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Skill Creator — build a reusable skill' })).toBeVisible();
    await expect(page.locator('main')).toContainText('skillhub/_guides/ghost-base/SKILL.md');
    await expect(page.locator('main')).toContainText('skillhub/_guides/skill-creation-guide/SKILL.md');
});

test('validator accepts recorder-compatible WebM locally and rejects oversize input', async ({ page }) => {
    await page.route('https://cdn.jsdelivr.net/**', route => route.abort());
    await page.goto('/skills/validate/');
    const input = page.getByLabel('Demo WebM (up to 3 MB, 30 seconds)');
    await input.setInputFiles(fileURLToPath(new URL('../../../tools/fixtures/demo.webm', import.meta.url)));
    await expect(page.locator('#demo-status')).toContainText('Demo accepted:');
    await expect(page.getByLabel('Demo video preview')).toBeVisible();
    await input.setInputFiles({ name: 'oversize.webm', mimeType: 'video/webm', buffer: Buffer.alloc(3_000_001) });
    await expect(page.locator('#demo-status')).toContainText('no larger than 3 MB');
    await expect(page.getByLabel('Demo video preview')).toBeHidden();
});
