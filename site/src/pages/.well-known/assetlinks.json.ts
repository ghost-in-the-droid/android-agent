// Digital Asset Links statement for Android App Links on HUB_DOMAIN.
// Values come from lib/hub/config.ts and are PLACEHOLDERs until the maintainer fills them
// from the release keystore (docs/app-links.md). scripts/check-assetlinks.mjs
// validates the emitted file after every build.
import type { APIRoute } from 'astro';
import { ANDROID_APP_PACKAGE, ANDROID_CERT_SHA256 } from '../../lib/hub/config';

export const GET: APIRoute = () =>
	new Response(
		JSON.stringify([
			{
				relation: ['delegate_permission/common.handle_all_urls'],
				target: { namespace: 'android_app', package_name: ANDROID_APP_PACKAGE, sha256_cert_fingerprints: ANDROID_CERT_SHA256 },
			},
		], null, 2) + '\n',
		{ headers: { 'Content-Type': 'application/json' } },
	);
