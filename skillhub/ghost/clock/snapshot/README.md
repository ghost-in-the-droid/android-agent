# Read-only Clock snapshot

`clock-snapshot.jar` is a small DEX JAR, not an APK or installed service. The
helper pushes it under a unique temporary name, runs the Android platform UI
Automator test runner as the adb shell user, then deletes it in `finally`.
It captures the active Google or Samsung Clock accessibility tree without an idle wait;
a running countdown or stopwatch would otherwise prevent a normal dump.

The source refuses another application's active window and includes visible nodes only and caps traversal at
2,000 nodes. It has no input injection, network, private-file read, settings
change or app-install code. XML is returned on stdout, never stored on-device.
The platform test runner tears down its temporary accessibility connection.
The additional platform `android.test.base.jar` classpath entry supplies the
legacy runner annotation that Samsung Android 13 otherwise cannot resolve.

Rebuild offline from the repository root with an already installed SDK:

```
python3 tools/build_clock_snapshot.py --sdk "$ANDROID_HOME" --build-tools 36.0.0
```

The reference build uses platform android-33, build-tools 36.0.0 and Java 8
bytecode. ZIP metadata is fixed for reproducible output with the same toolchain.
The source and binary are both included in the skill content digest. Rooted
emulators continue to validate their saved Clock preferences; unreadable prefs
use the UI fallback, which requires the correct timer label and a decreasing
countdown, or an increasing stopwatch with its Pause control exposed.
