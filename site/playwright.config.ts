import { defineConfig } from '@playwright/test';

// E2E for /showcase + landing (site/tests/e2e/).
// `cd site && npx playwright test` — builds nothing; serves the last
// `npm run build` output via astro preview. Set BASE_URL to test a
// deployed URL instead.
export default defineConfig({
	testDir: './tests/e2e',
	use: {
		baseURL: process.env.BASE_URL ?? 'http://localhost:4321',
	},
	webServer: process.env.BASE_URL
		? undefined
		: {
				command: 'npm run preview -- --port 4321',
				port: 4321,
				reuseExistingServer: true,
			},
});
