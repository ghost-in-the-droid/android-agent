# Android App Links for the Skill Hub

The hub QR code and install links use `https://<HUB_DOMAIN>/skills/install/<author>/<slug>@<version>`. Android opens that URL in the Ghost app only if the domain serves `/.well-known/assetlinks.json`, and that file has to name the app package and its signing certificate. Until those are filled in, the link opens the web fallback page, and that page offers a `ghost://install/...` link as a second option.

The site generates the file from `site/src/pages/.well-known/assetlinks.json.ts`. The values live in `site/src/lib/hub/config.ts` and are **PLACEHOLDER** today:

| Constant | Today | Fill with |
|---|---|---|
| `ANDROID_APP_PACKAGE` | `PLACEHOLDER.com.ghostinthedroid.portal` | The `applicationId` of the app that should open hub links. In this repo that is `com.ghostinthedroid.portal` (`portal/app/build.gradle.kts`). |
| `ANDROID_CERT_SHA256` | `PLACEHOLDER:00:...` | The SHA-256 fingerprint of the **release** signing certificate (see below). Add more than one entry to also accept a debug or upload key. |
| `HUB_DOMAIN` | `ghostinthedroid.com` | The domain that serves the hub (synthesis open call 4). |

## Get the SHA-256 from the release keystore

```bash
keytool -list -v -keystore /path/to/release.keystore -alias <release-alias>
```

Copy the `SHA256:` line from the "Certificate fingerprints" block. It looks like `AB:CD:...`: 32 uppercase hex pairs joined by colons. Paste it into `ANDROID_CERT_SHA256` and remove the `PLACEHOLDER` entry.

If the app ships through Google Play with Play App Signing, Play re-signs the app with its own key. In that case, use the "App signing key certificate" SHA-256 from Play Console under Setup, App integrity. You can list the upload key's fingerprint as well.

## The app side

The activity that handles installs needs an intent filter with `android:autoVerify="true"`. Without it, Android never checks the file:

```xml
<intent-filter android:autoVerify="true">
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data android:scheme="https" android:host="ghostinthedroid.com" android:pathPrefix="/skills/install/" />
</intent-filter>
<!-- Secondary custom scheme, not verifiable by Android; keep it as a fallback only -->
<intent-filter>
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data android:scheme="ghost" android:host="install" />
</intent-filter>
```

## Verify

- `npm run build` in `site/` runs `scripts/check-assetlinks.mjs` afterwards. The check fails the build if the file is missing, is not valid JSON, has the wrong shape, or contains a malformed fingerprint. It prints a reminder while the values are still placeholders.
- After deploying, test the live file with Google's checker: `https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://ghostinthedroid.com&relation=delegate_permission/common.handle_all_urls`
- To check on a phone, install a release build and run `adb shell pm verify-app-links --re-verify com.ghostinthedroid.portal`, then `adb shell pm get-app-links com.ghostinthedroid.portal`.
