// Skill Hub site constants. Everything that is still an open question for the maintainer
// (synthesis section 4) lives here so it changes in one place.

/** Domain that serves the hub and hosts `/.well-known/assetlinks.json`.
 *  OPEN QUESTION (synthesis 4.4): `ghostinthedroid.com/skills/` or a dedicated
 *  `skills.ghostinthedroid.com`. App Links must be verified on whichever wins. */
export const HUB_DOMAIN = 'ghostinthedroid.com';

/** Base of the verified Android App Link that the QR code encodes. The Ghost
 *  app claims this path prefix; browsers without the app land on the skill page. */
export const APP_LINK_BASE = `https://${HUB_DOMAIN}/skills/install`;

/** Android App Links verification (served at /.well-known/assetlinks.json).
 *  PLACEHOLDER values: the maintainer replaces both from the release keystore, see
 *  docs/app-links.md. The likely real package is `com.ghostinthedroid.portal`
 *  (portal/app/build.gradle.kts applicationId). */
export const ANDROID_APP_PACKAGE = 'PLACEHOLDER.com.ghostinthedroid.portal';
export const ANDROID_CERT_SHA256: string[] = [
	'PLACEHOLDER:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00',
];
export const ASSETLINKS_IS_PLACEHOLDER = ANDROID_APP_PACKAGE.startsWith('PLACEHOLDER') || ANDROID_CERT_SHA256.some((s) => s.startsWith('PLACEHOLDER'));

/** Custom-scheme fallback for phones where the App Link is not verified yet.
 *  Unverified by design (any app can claim it), so it is only a secondary link. */
export const CUSTOM_SCHEME = 'ghost';

/** GitHub org/repo that is the registry (contract section 2, GHOST_HUB_REPO default). */
export const HUB_REPO = 'ghost-in-the-droid/android-agent';

/** Minimum runs before a success rating is shown (synthesis D4 telemetry rule). */
export const MIN_RUNS_FOR_RATING = 20;

/** Window for the "recent" leaderboard and freshness. */
export const RECENT_WINDOW_DAYS = 90;

/** First-path-segment names under /skills/ that are not author handles. A
 *  GitHub user with one of these handles cannot publish under it. */
export const RESERVED_AUTHOR_NAMES = new Set([
	'overview', 'using-skills', 'creating-skills', 'elements', 'publishing',
	'showcase', 'leaderboard', 'scoring', 'validate', 'contribute', 'schema', 'install', 'search', 'icons', 'demos',
]);

export function appLinkFor(author: string, slug: string, version?: string): string {
	return `${APP_LINK_BASE}/${author}/${slug}${version ? `@${version}` : ''}`;
}

export function customSchemeLinkFor(author: string, slug: string, version?: string): string {
	return `${CUSTOM_SCHEME}://install/${author}/${slug}${version ? `@${version}` : ''}`;
}

export function installCommand(author: string, slug: string, version?: string): string {
	return `ghost skill install ${author}/${slug}${version ? `@${version}` : ''}`;
}

export function sourceUrl(author: string, slug: string, tag: string | null): string {
	return `https://github.com/${HUB_REPO}/tree/${tag ?? 'main'}/skillhub/${author}/${slug}`;
}

/** Immutable CDN URL of a released skill dir (contract Amendment A fetch order). */
export function cdnUrl(author: string, slug: string, tag: string | null): string {
	return `https://cdn.jsdelivr.net/gh/${HUB_REPO}@${tag ?? 'main'}/skillhub/${author}/${slug}`;
}
