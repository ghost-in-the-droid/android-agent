import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

// No human-assisted demo ships, and nothing enters scoring.
test('no human-assisted demo ships and none enters registry scoring', async ({ page, request }) => {
 const registryText = readFileSync(new URL('../../../skillhub/registry.json', import.meta.url), 'utf8');
 expect(registryText).not.toContain('/media/human-assisted/');
 await page.goto('/skills/ghost/calculator/');
 await expect(page.locator('[data-human-assisted-demo]')).toHaveCount(0);
 expect((await request.get('/media/human-assisted/signup.mp4')).status()).toBe(404);
});
