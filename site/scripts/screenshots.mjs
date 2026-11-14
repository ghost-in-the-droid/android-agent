// Run against npm run preview after npm run build. No network traffic is mocked.
import { chromium } from '@playwright/test';
import { mkdir, stat } from 'node:fs/promises';
import sharp from 'sharp';
import { showcasePages, showcaseViewports } from './showcase-pages.mjs';
const docsMode = process.argv.includes('--docs');
const output = new URL(docsMode ? '../test-results/docs-shots/' : '../test-results/showcase-shots/', import.meta.url);
await mkdir(output, { recursive: true });
const skillPageMode = process.argv.includes('--skillpage');
const showcaseOnly = process.argv.includes('--showcase');
const deviceGridMode = process.argv.includes('--devicegrid');
const promptsMode = process.argv.includes('--prompts');
const pages = docsMode ? ['/skills/scoring/', '/skills/using-skills/', '/skills/publishing/', '/features/mcp-server/'] : skillPageMode ? ['/skills/ghost/calculator/', '/skills/androidworld/pro-expense/', '/skills/'] : showcaseOnly ? ['/skills/showcase/'] : deviceGridMode ? ['/skills/androidworld/pro-expense/'] : promptsMode ? ['/skills/showcase/', '/skills/ghost/calculator/'] : showcasePages;
const browser = await chromium.launch();
const failures = [];
try {
 for (const viewport of showcaseViewports) for (const colorScheme of ['light', 'dark']) {
  const context = await browser.newContext({ viewport, colorScheme, deviceScaleFactor: 1 });
  for (const path of pages) {
   const page = await context.newPage();
   page.on('console', (message) => { if (message.type() === 'error') failures.push(`${path}: ${message.text()}`); });
   page.on('pageerror', (error) => failures.push(`${path}: ${error.message}`));
   const response = await page.goto(new URL(path, process.env.BASE_URL ?? 'http://localhost:4321').href, { waitUntil: 'networkidle' });
   if (!response?.ok()) failures.push(`${path}: HTTP ${response?.status()}`);
   if (path === '/skills/showcase/' && colorScheme === 'light') await page.locator('[data-theme-toggle]').click();
   if (promptsMode) {
    if (path === '/skills/showcase/') await page.locator('.showcase-details').first().locator('summary').click();
    else await page.locator('#tab-actions').click();
   }
   await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
   await page.mouse.move(0, 0);
   // Full-page captures include content below the viewport; load its lazy icons too.
   await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map(async (img) => { img.loading = 'eager'; await img.decode().catch(() => {}); }));
   });
   if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) failures.push(`${path}: horizontal overflow at ${viewport.width} ${colorScheme}`);
   const file = new URL(`${deviceGridMode ? 'devicegrid-' : promptsMode ? 'prompts-' : ''}${path.split('/').filter(Boolean).join('-')}-${viewport.width}-${colorScheme}.png`, output);
   const buffer = await page.screenshot(path === '/skills/' ? { clip: { x: 0, y: 0, width: viewport.width, height: Math.min(3000, await page.evaluate(() => document.documentElement.scrollHeight)) }, fullPage: true, animations: 'disabled' } : { fullPage: true, animations: 'disabled' });
   for (const colours of [128, 64, 32]) {
    await sharp(buffer).png({ palette: true, colours, compressionLevel: 9 }).toFile(file.pathname);
    if ((await stat(file)).size < 400 * 1024) break;
   }
   if ((await stat(file)).size >= 400 * 1024) failures.push(`${file.pathname}: screenshot exceeds 400 KB`);
   console.log(file.pathname);
   await page.close();
  }
  await context.close();
 }
} finally { await browser.close(); }
if (failures.length) { console.error(failures.join('\n')); process.exitCode = 1; }
