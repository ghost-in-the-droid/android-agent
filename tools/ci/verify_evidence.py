"""Bind independent verification artifacts, and new skillhub/SIGNERS lines, to the PR author's GitHub SSH keys.

The registry (tools/build_registry.py) counts only run artifacts whose signature verifies against
``skillhub/SIGNERS`` (community principals) or ``skillhub/verifier-keys.yml`` (official and platform
principals). This guard is what makes a SIGNERS line trustworthy: a PR may add lines only for its own
author's login, and only with keys published on that GitHub account.
"""

import argparse
import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

import yaml

from gitd.skills.engine.evidence import artifact_binding_rejection
from gitd.skills.engine.manifest import has_python_helpers

LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
NAMESPACE = "ghost-skill-run"
MAX_ARTIFACT_BYTES = 1_000_000
SIGNERS_PATH = "skillhub/SIGNERS"
SIGNERS_LINE = re.compile(r'(?P<principal>\S+)\s+namespaces="' + NAMESPACE + r'"\s+(?P<key>\S+\s+\S+)(\s+\S.*)?')


def verification_paths(paths):
    result = []
    for path in paths:
        parts = PurePosixPath(path).parts
        if len(parts) == 5 and parts[0] == "skillhub" and parts[3] == "verifications" and parts[4].endswith(".json"):
            result.append(path)
    return sorted(set(result))


def changed_verifications(base, head="HEAD"):
    command = ["git", "diff", "--name-only", "--no-renames", "--diff-filter=AMT", "-z", base, head, "--", "skillhub/"]
    return verification_paths(subprocess.check_output(command).decode().split("\0"))


def only_verifications(paths):
    paths = [path for path in paths if path]
    return bool(paths) and set(paths) == set(verification_paths(paths))


def fetch_author_keys(actor):
    if not LOGIN.fullmatch(actor):
        raise ValueError("Invalid PR author login")
    with urllib.request.urlopen(f"https://github.com/{actor}.keys", timeout=20) as response:
        keys = response.read(1_000_001)
    if len(keys) > 1_000_000:
        raise ValueError("GitHub public key response exceeds size limit")
    result = []
    for line in keys.decode("utf-8").splitlines():
        # Only accept literal public-key lines, never allowed_signers options.
        fields = line.split()
        if len(fields) >= 2 and fields[0] in (
            "ssh-ed25519",
            "ssh-rsa",
            "ecdsa-sha2-nistp256",
            "ecdsa-sha2-nistp384",
            "ecdsa-sha2-nistp521",
            "sk-ssh-ed25519@openssh.com",
            "sk-ecdsa-sha2-nistp256@openssh.com",
        ):
            result.append(" ".join(fields[:2]))
    if not result:
        raise ValueError(f"PR author {actor} has no usable GitHub SSH public keys")
    return result


def signers_changed(base, head="HEAD"):
    command = ["git", "diff", "--name-only", "--no-renames", "-z", base, head, "--", SIGNERS_PATH]
    return SIGNERS_PATH in subprocess.check_output(command).decode().split("\0")


def signers_diff(base, head="HEAD"):
    """(added, removed) non-comment lines of skillhub/SIGNERS between base and head."""

    def lines(rev):
        try:
            text = subprocess.check_output(["git", "show", f"{rev}:{SIGNERS_PATH}"], stderr=subprocess.DEVNULL).decode(
                "utf-8"
            )
        except subprocess.CalledProcessError:
            return []
        return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]

    before, after = lines(base), lines(head)
    return [ln for ln in after if ln not in before], [ln for ln in before if ln not in after]


def check_signers_lines(added, removed, actor, public_keys):
    """Every added or removed SIGNERS line must name the PR author, in the run namespace, with a key on
    that author's GitHub account (added lines). Returns the accepted principals."""
    if not LOGIN.fullmatch(actor):
        raise ValueError("Invalid PR author login")
    published = {" ".join(key.split()[:2]) for key in public_keys}
    for line in added:
        match = SIGNERS_LINE.fullmatch(line)
        if not match:
            raise ValueError(f'SIGNERS line is not "<login> namespaces="{NAMESPACE}" <keytype> <key>": {line[:80]}')
        if match.group("principal") != actor:
            raise ValueError("SIGNERS lines may only be added for the PR author login")
        if " ".join(match.group("key").split()[:2]) not in published:
            raise ValueError("SIGNERS key is not published on the PR author GitHub account")
    for line in removed:
        match = SIGNERS_LINE.fullmatch(line)
        if not match or match.group("principal") != actor:
            raise ValueError("SIGNERS lines may only be removed by their own principal")
    return [actor] if added or removed else []


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify_artifact(path, actor, public_keys, skill_author):
    if not LOGIN.fullmatch(actor):
        raise ValueError("Invalid PR author login")
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("Verification must be a regular JSON file within the size limit")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Verification must contain valid UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Verification must be a JSON object")
    if data.get("verifier") != actor:
        raise ValueError("Signed verifier field must equal the PR author login")
    if "github_login" in data and data["github_login"] != actor:
        raise ValueError("Signed github_login field must equal the PR author login")
    if not re.fullmatch(re.escape(actor) + r"-[0-9a-f]{64}-.+\.json", path.name):
        raise ValueError("Verification filename prefix must equal the PR author login")
    if actor.casefold() == skill_author.casefold():
        raise ValueError("A skill author cannot independently verify their own skill")
    signature = data.pop("signature", None)
    if not isinstance(signature, dict) or signature.get("namespace") != NAMESPACE:
        raise ValueError("Verification requires an SSH signature in the ghost-skill-run namespace")
    if signature.get("principal", actor) != actor:
        raise ValueError("SSH signature principal must equal the PR author login")
    value = signature.get("value")
    if not isinstance(value, str) or not value.startswith("-----BEGIN SSH SIGNATURE-----"):
        raise ValueError("Verification requires a valid SSH signature value")
    if not public_keys:
        raise ValueError("PR author has no SSH public keys")
    with tempfile.TemporaryDirectory(prefix="ghost-verification-") as temporary:
        root = Path(temporary)
        allowed = root / "allowed_signers"
        allowed.write_text(
            "".join(f'{actor} namespaces="{NAMESPACE}" {key}\n' for key in public_keys), encoding="utf-8"
        )
        sig_file = root / "evidence.sig"
        sig_file.write_text(value, encoding="utf-8")
        try:
            verified = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", str(allowed), "-I", actor, "-n", NAMESPACE, "-s", str(sig_file)],
                input=canonical(data),
                capture_output=True,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f"SSH signature verification unavailable: {exc}") from exc
        if verified.returncode:
            raise ValueError("SSH signature does not verify for the PR author public keys and principal")
    metadata = yaml.safe_load((path.parent.parent / "skill.yaml").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("skill.yaml must be a mapping")
    reason = artifact_binding_rejection(data, metadata, has_python=has_python_helpers(path.parent.parent))
    if reason:
        raise ValueError(reason)
    return path.as_posix()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--actor", required=True)
    args = parser.parse_args()
    paths = changed_verifications(args.base, args.head)
    signers = signers_changed(args.base, args.head)
    if not paths and not signers:
        print("No added or modified independent verification artifacts or SIGNERS lines")
        return 0
    try:
        public_keys = fetch_author_keys(args.actor)
        if signers:
            added, removed = signers_diff(args.base, args.head)
            check_signers_lines(added, removed, args.actor, public_keys)
            print(f"Verified SIGNERS change: {len(added)} added, {len(removed)} removed, principal {args.actor}")
        for name in paths:
            path = Path(name)
            if not path.resolve().is_relative_to(Path.cwd().resolve()):
                raise ValueError("Verification must stay within the checkout")
            spec = path.parent.parent / "skill.yaml"
            metadata = yaml.safe_load(spec.read_text())
            if not isinstance(metadata, dict):
                raise ValueError("skill.yaml must be a mapping")
            author = metadata.get("author", path.parts[1])
            if not isinstance(author, str) or not author:
                raise ValueError("Skill author must be a nonempty string")
            if args.actor.casefold() == path.parts[1].casefold():
                raise ValueError("A skill author cannot independently verify their own skill")
            verify_artifact(path, args.actor, public_keys, author)
            print(f"Verified independent artifact: {name}")
    except (ValueError, OSError, yaml.YAMLError) as exc:
        print(f"Verification rejected: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
