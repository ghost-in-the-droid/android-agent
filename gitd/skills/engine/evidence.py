"""Concrete fingerprint collection and locally signed, privacy-scoped run evidence.

SSH signatures establish integrity under a local key. GitHub account ownership
and independence are checked by reviewers/CI, not inferred from the signature.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from gitd.skills.engine.fingerprint import version_matches

NAMESPACE = "ghost-skill-run"
BENCH_ARMS = ("before", "after_replay", "after_mcp")
LOGIN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")


def canonical(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def signing_public_key() -> str:
    """Public half of the local run-signing key (generated on first use)."""
    key = _ensure_signing_key()
    return subprocess.run(
        ["ssh-keygen", "-y", "-f", str(key)], check=True, capture_output=True, text=True, timeout=20
    ).stdout.strip()


def signers_line(principal: str, public_key: str) -> str:
    """One allowed_signers line binding ``principal`` to ``public_key`` in the run namespace."""
    if not LOGIN_RE.fullmatch(principal):
        raise ValueError("Invalid signer principal")
    fields = public_key.split()
    if len(fields) < 2 or not fields[0].startswith(("ssh-", "ecdsa-", "sk-")):
        raise ValueError("Invalid SSH public key")
    return f'{principal} namespaces="{NAMESPACE}" {fields[0]} {fields[1]}\n'


def verify_signature(payload: dict, signature: dict, allowed_signers: Path, principal: str) -> bool:
    """True when ``signature`` is a valid SSH signature over canonical ``payload`` by a key that
    ``allowed_signers`` lists for ``principal`` in the run namespace. Missing ssh-keygen = False."""
    value = signature.get("value") if isinstance(signature, dict) else None
    if not isinstance(value, str) or not value.startswith("-----BEGIN SSH SIGNATURE-----"):
        return False
    if not LOGIN_RE.fullmatch(principal) or not shutil.which("ssh-keygen"):
        return False
    with tempfile.TemporaryDirectory(prefix="ghost-verify-") as temporary:
        sig_file = Path(temporary) / "evidence.sig"
        sig_file.write_text(value, encoding="utf-8")
        try:
            result = subprocess.run(
                [
                    "ssh-keygen",
                    "-Y",
                    "verify",
                    "-f",
                    str(allowed_signers),
                    "-I",
                    principal,
                    "-n",
                    NAMESPACE,
                    "-s",
                    str(sig_file),
                ],
                input=canonical(payload),
                capture_output=True,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            return False
    return result.returncode == 0


def bench_block_error(block) -> str | None:
    """Shape check for the optional nested ``bench`` block (display only, never points)."""
    if not isinstance(block, dict):
        return "bench block must be an object"
    for key in ("suite", "task_id", "arm"):
        if not isinstance(block.get(key), str) or not block[key]:
            return f"bench.{key} must be a nonempty string"
    if block["arm"] not in BENCH_ARMS:
        return "bench.arm must be one of " + ", ".join(BENCH_ARMS)
    for key in ("seed", "steps", "tokens", "wall_ms"):
        if key in block and (type(block[key]) is not int or block[key] < 0):
            return f"bench.{key} must be a non-negative integer"
    for key in ("trace_path", "screenshots_path"):
        if key in block and not isinstance(block[key], str):
            return f"bench.{key} must be a string"
    return None


def _app_fingerprints(metadata: dict) -> list[dict]:
    fp = metadata.get("fingerprint")
    if isinstance(fp, list):
        return [item for item in fp if isinstance(item, dict)]
    if isinstance(fp, dict):
        return [fp]
    return [
        {
            "app_package": metadata.get("android_package")
            or metadata.get("app_package")
            or metadata.get("ios_bundle_id"),
            "app_version": metadata.get("app_version_tested"),
        }
    ]


def artifact_binding_rejection(data: dict, metadata: dict, *, has_python: bool = False) -> str | None:
    """Shared app binding policy for registry runs and PR verification artifacts.

    Legacy artifacts may omit package fields; every package they do name must be declared.
    """
    fingerprints = _app_fingerprints(metadata)
    packages = {
        str(package) for fp in fingerprints for package in [fp.get("app_package"), *(fp.get("apps") or [])] if package
    }
    recorded = data.get("fingerprint")
    recorded = recorded if isinstance(recorded, dict) else {}
    named = [source.get("app_package") for source in (recorded, data) if source.get("app_package")]
    if packages and any(not isinstance(package, str) or package not in packages for package in named):
        return "wrong-app"
    sources = [source for source in (recorded, data) if "app_version" in source] or [recorded]
    for source in sources:
        package = source.get("app_package") or recorded.get("app_package") or data.get("app_package")
        applicable = [
            fp
            for fp in fingerprints
            if not package or package == fp.get("app_package") or package in (fp.get("apps") or [])
        ]
        # The app_version declaration belongs to the primary package, not its companion apps.
        if applicable and all(
            (not package or package == fp.get("app_package"))
            and not version_matches(str(fp.get("app_version") or "*"), str(source.get("app_version") or ""))
            for fp in applicable
        ):
            return "stale-app"
    digest = data.get("skill_sha256")
    if has_python and (not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)):
        return "unbound-helper"
    return None


def artifact_rejection(
    data: dict,
    *,
    skill_ref: str,
    principal: str,
    allowed_signers: Path,
    metadata: dict | None = None,
    has_python: bool = False,
) -> str | None:
    """Why a run artifact must not count as evidence, or None when it verifies.

    Reasons: unsigned, simulated, wrong-skill, wrong-app, stale-app, unbound-helper,
    bad-bench-block, bad-signature (unknown key,
    tampered payload, wrong principal or namespace, ssh-keygen unavailable: all fail closed).
    """
    signature = data.get("signature")
    if not isinstance(signature, dict) or signature.get("namespace") != NAMESPACE or not signature.get("value"):
        return "unsigned"
    if data.get("simulation") or data.get("device_backend") not in (None, "device"):
        return "simulated"
    if data.get("skill") != skill_ref:
        return "wrong-skill"
    if "bench" in data and bench_block_error(data["bench"]):
        return "bad-bench-block"
    reason = artifact_binding_rejection(data, metadata or {}, has_python=has_python)
    if reason:
        return reason
    payload = {key: value for key, value in data.items() if key != "signature" and not key.startswith("_")}
    if not verify_signature(payload, signature, allowed_signers, principal):
        return "bad-signature"
    return None


def fingerprint_hash(fingerprint: dict) -> str:
    return hashlib.sha256(canonical(fingerprint)).hexdigest()


def validate_fingerprint(fingerprint: dict) -> dict:
    if not isinstance(fingerprint, dict):
        raise ValueError("Fingerprint must be a JSON object")
    required = ("os", "os_version", "hardware", "app_package", "app_version")
    fields = (*required, "screen_wxh", "density", "locale", "theme")
    result = {key: fingerprint[key] for key in fields if key in fingerprint}
    for key in required:
        value = result.get(key)
        if not isinstance(value, str) or not value.strip() or any(c in value for c in "*<>~="):
            raise ValueError(f"Recorded fingerprint requires a concrete {key}")
        result[key] = value.strip()
    if result["os"] not in {"android", "ios"}:
        raise ValueError("Fingerprint os must be android or ios")
    return result


def collect_fingerprint(skill, serial: str, supplied: str | None = None) -> dict:
    if serial.startswith("fake:"):
        from gitd.skills.engine.fake_device import FakeDevice

        fingerprint = validate_fingerprint(FakeDevice(serial).fingerprint)
        if fingerprint["app_package"] != skill.fingerprint.app_package:
            raise ValueError("Fake fixture fingerprint must match the target app")
        if supplied and validate_fingerprint(json.loads(Path(supplied).read_text())) != fingerprint:
            raise ValueError("Supplied fingerprint must match the fake fixture")
        return fingerprint
    if supplied:
        fingerprint = validate_fingerprint(json.loads(Path(supplied).read_text()))
        expected_os = "ios" if serial.startswith("ios:") else "android"
        if fingerprint["os"] != expected_os or fingerprint["app_package"] != skill.fingerprint.app_package:
            raise ValueError("Supplied fingerprint must match device platform and target app")
        return fingerprint
    if serial.startswith("ios:"):
        raise ValueError("iOS recording requires --fingerprint <concrete-fingerprint.json>")

    def shell(*arguments):
        try:
            return subprocess.run(
                ["adb", "-s", serial, "shell", *arguments], check=True, capture_output=True, text=True, timeout=20
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"Cannot collect device fingerprint: {exc}") from exc

    app_package = skill.fingerprint.app_package
    package_info = shell("dumpsys", "package", app_package)
    version = re.search(r"^\s*versionName=(\S+)", package_info, re.M)
    if not version:
        raise ValueError(f"Cannot determine installed app version: {app_package}")
    values = {
        "os": "android",
        "os_version": shell("getprop", "ro.build.version.release"),
        "hardware": shell("getprop", "ro.product.manufacturer") + "/" + shell("getprop", "ro.product.model"),
        "app_package": app_package,
        "app_version": version.group(1),
    }
    values.update(_display_axes(shell))
    return validate_fingerprint(values)


def _display_axes(shell) -> dict:
    """Best-effort screen, density and locale for the compatibility matrix; a field that cannot be read is omitted."""
    axes = {}
    try:
        size = shell("wm", "size")
        found = re.findall(r"(?:Override|Physical) size:\s*(\d+x\d+)", size)
        if found:
            axes["screen_wxh"] = found[-1] if "Override" in size else found[0]
        density = shell("wm", "density")
        dens = re.findall(r"(?:Override|Physical) density:\s*(\d+)", density)
        if dens:
            axes["density"] = dens[-1] if "Override" in density else dens[0]
        locale = shell("getprop", "persist.sys.locale") or shell("getprop", "ro.product.locale")
        if re.fullmatch(r"[a-z]{2,3}(-[A-Za-z0-9]{2,8})*", locale or ""):
            axes["locale"] = locale
    except Exception:  # best effort: a device that cannot report these still records a valid run
        pass
    return axes


def detect_emulator(serial: str) -> bool | None:
    """True when the Android device behind ``serial`` is a virtual device (``ro.kernel.qemu`` or
    ``ro.boot.qemu`` is 1), False on hardware, None when it cannot be read (fake devices, iOS, adb errors)."""
    if not serial or serial.startswith(("fake:", "ios:")):
        return None
    try:
        out = subprocess.run(
            ["adb", "-s", serial, "shell", "getprop ro.kernel.qemu; getprop ro.boot.qemu"],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return any(value.strip() == "1" for value in out)


def github_login() -> str:
    try:
        login = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"], check=True, capture_output=True, text=True, timeout=20
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Cannot identify verifier; authenticate gh first: {exc}") from exc
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", login):
        raise ValueError("Invalid GitHub verifier login")
    return login


def _ensure_signing_key() -> Path:
    """Path of the persistent local Ed25519 run-signing key, generated on first use."""
    from gitd.ghostcli.config import ghost_dir

    directory = ghost_dir()
    directory.mkdir(parents=True, exist_ok=True)
    key = directory / "run-signing-key"
    if key.exists():
        return key
    try:
        # Generate into a private temp dir so failed generation leaves no key.
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            generated = Path(temporary) / "key"
            subprocess.run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", NAMESPACE, "-f", str(generated)],
                check=True,
                capture_output=True,
                timeout=20,
            )
            # Exclusive creation avoids replacing a concurrent recorder's key.
            try:
                with key.open("xb") as out:
                    key.chmod(0o600)
                    out.write(generated.read_bytes())
            except FileExistsError:
                pass
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Cannot create the run-signing key; ssh-keygen is required: {exc}") from exc
    return key


def _sign(payload: dict) -> dict:
    """Sign canonical JSON with a persistent local Ed25519 SSH key."""
    key = _ensure_signing_key()
    directory = key.parent
    try:
        public_key = subprocess.run(
            ["ssh-keygen", "-y", "-f", str(key)], check=True, capture_output=True, text=True, timeout=20
        ).stdout.strip()
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            source = Path(temporary) / "payload.json"
            source.write_bytes(canonical(payload))
            subprocess.run(
                ["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", NAMESPACE, str(source)],
                check=True,
                capture_output=True,
                timeout=20,
            )
            signature = Path(str(source) + ".sig").read_text()
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Cannot sign run evidence; ssh-keygen with SSH signing support is required: {exc}") from exc
    return {"algorithm": "ssh-ed25519", "namespace": NAMESPACE, "public_key": public_key, "value": signature}


def write_evidence(
    skill,
    results: list,
    fingerprint: dict,
    *,
    login: str | None = None,
    artifact_dir: Path | None = None,
    simulated: bool = False,
    bench: dict | None = None,
    model: str = "deterministic",
    emulator: bool | None = None,
) -> Path:
    """Write a signed run artifact. ``emulator`` is True on a virtual device (``detect_emulator``), False on
    hardware, None when unknown; the registry never treats an unknown as hardware."""
    from gitd.skills.engine.manifest import skill_content_digest

    fingerprint = validate_fingerprint(fingerprint)
    if bench is not None and bench_block_error(bench):
        raise ValueError("Invalid bench block: " + bench_block_error(bench))
    if fingerprint["app_package"] != skill.fingerprint.app_package:
        raise ValueError("Evidence fingerprint does not match target app")
    if login is not None and not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", login):
        raise ValueError("Invalid verifier login")
    if login is not None and login.casefold() == skill.author.casefold():
        raise ValueError("Independent verification requires an account other than the skill author")
    now = datetime.now(timezone.utc)
    digest = fingerprint_hash(fingerprint)
    payload = {
        "schema_version": 1,
        "kind": "verification" if login else "self-run",
        "skill": f"{skill.author}/{skill.name}",
        "version": skill.version,
        "fingerprint": fingerprint,
        "fingerprint_hash": digest,
        "app_version": fingerprint["app_version"],
        "model": model,
        "timestamp": now.isoformat(),
        "finished_at": now.isoformat(),
        "device_class": fingerprint["hardware"] + "/" + fingerprint["os_version"].split(".")[0],
        "success": all(result.success for result in results),
        "actions": [],
        "device_backend": "fake" if simulated else "device",
        "simulation": simulated,
        # Pins the run to the exact shipped bytes; the registry counts a run only for the code on disk.
        "skill_sha256": skill_content_digest(skill.skill_dir),
        "emulator": emulator,
    }
    if login:
        payload["github_login"] = login
        payload["verifier"] = login
        payload["verifier_tier"] = "novice"
    if bench is not None:
        payload["bench"] = dict(bench)
    for result in results:
        payload["actions"].append(
            {
                "name": result.action,
                "success": result.success,
                "duration_ms": result.duration_ms,
                "error_kind": (result.error or {}).get("kind"),
                "asks": result.data.get("asks", []),
                "steps": [
                    {"index": t.step_index, "success": t.error is None, "duration_ms": t.duration_ms}
                    for t in result.trace
                ],
            }
        )
    payload["signature"] = _sign(payload)
    root = artifact_dir if artifact_dir is not None else skill.skill_dir / ("verifications" if login else "runs")
    root.mkdir(parents=True, exist_ok=True)
    prefix = f"{login}-" if login else ""
    destination = root / f"{prefix}{digest}-{now.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    with destination.open("x", encoding="utf-8") as out:
        json.dump(payload, out, indent=2)
        out.write("\n")
    return destination
