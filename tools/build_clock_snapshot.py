#!/usr/bin/env python3
"""Rebuild the read-only Clock UI snapshot JAR using an existing Android SDK; no downloads."""

import argparse
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, default=os.environ.get("ANDROID_HOME"))
    parser.add_argument("--platform", default="android-33")
    parser.add_argument("--build-tools", default="34.0.0")
    args = parser.parse_args()
    if not args.sdk:
        parser.error("pass --sdk or set ANDROID_HOME to an existing SDK")
    root = Path(__file__).resolve().parents[1] / "skillhub/ghost/clock/snapshot"
    platform = args.sdk / "platforms" / args.platform
    libraries = [platform / "android.jar", platform / "uiautomator.jar", platform / "optional/android.test.base.jar"]
    with tempfile.TemporaryDirectory(prefix="clock-snapshot-") as folder:
        subprocess.run(
            [
                "javac",
                "-J-Xmx128m",
                "-J-XX:ActiveProcessorCount=2",
                "-source",
                "8",
                "-target",
                "8",
                "-cp",
                os.pathsep.join(map(str, libraries)),
                "-d",
                folder,
                str(root / "ClockSnapshot.java"),
            ],
            check=True,
        )
        subprocess.run(
            [
                "java",
                "-Xmx128m",
                "-XX:ActiveProcessorCount=2",
                "-cp",
                str(args.sdk / "build-tools" / args.build_tools / "lib/d8.jar"),
                "com.android.tools.r8.D8",
                "--min-api",
                "23",
                "--output",
                folder,
                str(Path(folder) / "ghost/clock/ClockSnapshot.class"),
            ],
            check=True,
        )
        # Stable ZIP metadata makes two builds with the same toolchain byte-identical.
        target = Path(folder) / "clock-snapshot.jar"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr(
                zipfile.ZipInfo("classes.dex", (1980, 1, 1, 0, 0, 0)), (Path(folder) / "classes.dex").read_bytes()
            )
        os.replace(target, root / "clock-snapshot.jar")


if __name__ == "__main__":
    main()
