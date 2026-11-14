"""Ghost Skill Hub install client.

The hub is the ``skillhub/`` folder of the hub repo (``GHOST_HUB_REPO``, default
``ghost-in-the-droid/android-agent``); ``skillhub/registry.json`` indexes it
(schema: see tools/build_registry.py).

Install flow for ``install("alice/demo@1.2.0")``:
  1. fetch ``registry.json`` (from ``main``), find ``alice/demo`` and the version
  2. trust gate: official/verified silent (verified prints a note), quarantined
     blocked unless ``force``, unverified (any ``source`` outside the hub repo)
     prints a warning and needs ``yes=True`` or an interactive ``y``
  3. download every file in the version's ``files`` map, pinned to the
     version's commit sha (else its tag ``<author>/<slug>-v<version>``):
     jsDelivr ``@<rev>`` first, the GitHub Release tarball
     ``<author>-<slug>-v<version>.tar.gz`` second, raw.githubusercontent never
     (Amendment A). ``@main`` is only used for ``registry.json`` discovery and
     for an explicit ``@main`` ref. Verify each sha256
  4. write ``$GHOST_SKILLS_DIR/<author>/<slug>/<version>/`` atomically and point
     ``@latest`` (symlink, or ``latest.txt`` where symlinks fail) at the highest
     installed version

``source`` may be a base URL (``file://``, ``http(s)://``) of a checkout or
mirror laid out like the hub repo (``<base>/skillhub/registry.json``). It is
treated as unverified unless it is the configured hub repo itself.

Network goes through ``_fetch`` (urllib, 20s timeout); tests monkeypatch it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable

from gitd.skills.locations import installed_skills_dir
from gitd.skills.refs import MAIN, SkillRef, is_semver, max_version, parse_ref, version_key

log = logging.getLogger(__name__)

DEFAULT_HUB_REPO = "ghost-in-the-droid/android-agent"
TIMEOUT_S = 20
INSTALL_META = ".ghost-install.json"
TRUST_TIERS = ("official", "benchmark", "verified", "unverified", "quarantined")

UNVERIFIED_WARNING = (
    "UNVERIFIED skill {ref}. Contains Python code that will run on your machine and phone.\n"
    "Review at {url} before installing."
)

STATUS_WARNINGS = {
    "blocked": (
        "WARNING: {ref} is marked BLOCKED: it cannot complete autonomously right now "
        "(for example a mandatory phone check or CAPTCHA). Installing anyway; see its README for the blocker."
    ),
    "deprecated": "WARNING: {ref} is DEPRECATED and may be removed from the hub. Look for a replacement.",
    "draft": (
        "WARNING: {ref} is a DRAFT scaffold: its steps and validators are not authored yet, so it will not "
        "replay. Installing anyway; see its README and SOFT.md."
    ),
}
DESTRUCTIVE_WARNING = (
    "DESTRUCTIVE skill {ref}: it can change or delete data on the device or accounts "
    "(side effects: {effects}). It gates the risky step behind confirm_before or dry_run."
)


class HubError(Exception):
    """Install/registry failure with a user-facing message."""


class TrustDeclined(HubError):
    """User declined (or could not confirm) an unverified or quarantined install."""


@dataclass
class InstalledSkill:
    author: str
    slug: str
    version: str
    path: Path
    trust: str = "unverified"
    source: str = ""
    rev: str = ""
    installed_at: str = ""
    files: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.author}/{self.slug}"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["path"] = str(self.path)
        return d


# ── network ─────────────────────────────────────────────────────────────────


def hub_repo() -> str:
    return os.environ.get("GHOST_HUB_REPO", DEFAULT_HUB_REPO).strip("/")


def _fetch(url: str) -> bytes:
    """GET ``url`` (http/https/file). Raises HubError on any failure."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_S) as resp:  # noqa: S310 (scheme checked by caller)
            return resp.read()
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise HubError(f"fetch failed: {url}: {e}") from e


def _urls_for(path: str, *, rev: str, source: str | None) -> list[str]:
    """Candidate URLs for a repo-relative ``path`` at ``rev``. Hub: jsDelivr only, never raw GitHub."""
    if source:
        return [f"{source.rstrip('/')}/{path}"]
    return [f"https://cdn.jsdelivr.net/gh/{hub_repo()}@{rev}/{path}"]


def release_asset_name(author: str, slug: str, version: str) -> str:
    return f"{author}-{slug}-v{version}.tar.gz"


def release_asset_url(tag: str, author: str, slug: str, version: str) -> str:
    return f"https://github.com/{hub_repo()}/releases/download/{tag}/{release_asset_name(author, slug, version)}"


def _files_from_release(url: str, slug: str) -> dict[str, bytes]:
    """Download a release tarball; return ``{relpath: bytes}``. Members may sit under ``<slug>/``."""
    import io

    blob = _fetch(url)
    out: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tf:
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                name = m.name[2:] if m.name.startswith("./") else m.name
                if name.startswith(slug + "/"):
                    name = name[len(slug) + 1 :]
                f = tf.extractfile(m)
                if f is not None:
                    out[name] = f.read()
    except (tarfile.TarError, OSError) as e:
        raise HubError(f"release asset {url} is not a readable tarball: {e}") from e
    return out


def _get(path: str, *, rev: str, source: str | None) -> bytes:
    errors = []
    for url in _urls_for(path, rev=rev, source=source):
        try:
            return _fetch(url)
        except HubError as e:
            errors.append(str(e))
    raise HubError("; ".join(errors))


def _normalize_source(source: str | None) -> str | None:
    """Accept a base URL or a local dir path; return a URL base or None for the hub."""
    if not source:
        return None
    if "://" not in source:
        p = Path(source).expanduser().resolve()
        if not p.exists():
            raise HubError(f"source {source!r} is neither a URL nor an existing directory")
        return p.as_uri()
    scheme = source.split("://", 1)[0].lower()
    if scheme not in ("http", "https", "file"):
        raise HubError(f"unsupported source scheme {scheme!r}: use https://, http:// or file://")
    source = source.rstrip("/")
    if source.endswith(".git"):
        source = source[:-4]
    # https://github.com/<org>/<repo>[/tree/<rev>] -> jsDelivr file base (raw GitHub is never used)
    if source.startswith("https://github.com/"):
        parts = source[len("https://github.com/") :].split("/")
        if len(parts) < 2:
            raise HubError(f"source {source!r}: expected https://github.com/<org>/<repo>")
        rev = parts[3] if len(parts) >= 4 and parts[2] == "tree" else MAIN
        source = f"https://cdn.jsdelivr.net/gh/{parts[0]}/{parts[1]}@{rev}"
    return source


def _is_hub_source(source: str | None) -> bool:
    if source is None:
        return True
    repo = hub_repo()
    # Exact repo match: the prefix must be followed by end, "@" (jsDelivr rev) or "/main" style root only.
    # A different repo sharing the prefix, or a non-main tree rev, is NOT the hub.
    for p in (
        f"https://github.com/{repo}",
        f"https://raw.githubusercontent.com/{repo}",
        f"https://cdn.jsdelivr.net/gh/{repo}",
    ):
        if source == p:
            return True
        if source.startswith(p) and source[len(p)] in "@/":
            rest = source[len(p) + 1 :]
            if source[len(p)] == "@":
                if rest in ("", MAIN):
                    return True
            elif rest in ("", MAIN) or rest == f"tree/{MAIN}":
                return True
    return False


def fetch_registry(source: str | None = None) -> dict:
    """Download and parse ``skillhub/registry.json`` from ``main`` (or ``source``)."""
    src = _normalize_source(source)
    if src is not None and _is_hub_source(src):
        src = None
    raw = _get("skillhub/registry.json", rev=MAIN, source=src)
    try:
        reg = json.loads(raw)
    except ValueError as e:
        raise HubError(f"registry.json is not valid JSON: {e}") from e
    if not isinstance(reg, dict) or not isinstance(reg.get("skills"), dict):
        raise HubError("registry.json missing `skills` map")
    return reg


# ── install helpers ─────────────────────────────────────────────────────────


def _safe_rel(name: str) -> PurePosixPath:
    rel = PurePosixPath(name)
    if not name or rel.is_absolute() or ".." in rel.parts or "\\" in name:
        raise HubError(f"refusing unsafe file path in registry: {name!r}")
    return rel


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _rev_for(ref: SkillRef, version: str, vinfo: dict) -> str:
    """The version's commit sha, else its tag; ``main`` only for an explicit ``@main`` ref.

    The sha is preferred: it is immutable and has no ``/`` (tags look like
    ``<author>/<slug>-v<version>``, which jsDelivr's ``@<rev>`` cannot carry).
    """
    if ref.version == MAIN:
        return MAIN
    rev = vinfo.get("commit") or vinfo.get("tag")
    if not rev:
        raise HubError(f"{ref.key}@{version}: registry records no commit or tag to pin the download to")
    return rev


def _download_verified(
    r: SkillRef, version: str, vinfo: dict, files: dict, *, rev: str, source: str | None
) -> dict[PurePosixPath, bytes]:
    """Fetch every file (jsDelivr, then the release tarball for the hub) and verify sha256."""
    rels = {name: _safe_rel(name) for name in files}

    def verify(name: str, data: bytes) -> bytes:
        got = _sha256(data)
        if got != files[name]:
            raise HubError(f"sha256 mismatch for {r.key}@{version}/{name}: registry {files[name]}, got {got}")
        return data

    blobs: dict[PurePosixPath, bytes] = {}
    try:
        for name in sorted(files):
            blobs[rels[name]] = verify(name, _get(f"skillhub/{r.author}/{r.slug}/{rels[name]}", rev=rev, source=source))
        return blobs
    except HubError as first:
        tag = vinfo.get("tag")
        if source is not None or not tag or "sha256 mismatch" in str(first):
            raise
        url = release_asset_url(tag, r.author, r.slug, version)
        log.warning("jsDelivr fetch failed (%s); trying release asset %s", first, url)
        try:
            tar_files = _files_from_release(url, r.slug)
        except HubError as second:
            raise HubError(f"{first}; {second}") from second
        for name in sorted(files):
            if name not in tar_files:
                raise HubError(f"release asset {url} lacks {name}")
            blobs[rels[name]] = verify(name, tar_files[name])
        return blobs


def _trust_gate(
    ref_text: str, trust: str, *, url: str, yes: bool, force: bool, confirm: Callable[[str], bool] | None, author: str
) -> None:
    if trust == "quarantined":
        if not force:
            raise TrustDeclined(f"{ref_text} is quarantined by the registry; pass force=True (--force) to override")
        print(f"WARNING: installing quarantined skill {ref_text} (forced)", file=sys.stderr)
        return
    if trust == "official":
        return
    if trust == "verified":
        print(f"Installing verified community skill by @{author}")
        return
    if trust == "benchmark":
        print(f"Installing benchmark reference skill {ref_text} (imported scaffold, maintainer-owned)")
        return
    print(UNVERIFIED_WARNING.format(ref=ref_text, url=url), file=sys.stderr)
    if yes:
        return
    ask = confirm or _ask_tty
    if not ask("Continue? (y/N) "):
        raise TrustDeclined(f"install of unverified skill {ref_text} declined")


def install_card(key: str, version: str, entry: dict, vinfo: dict, trust: str) -> str:
    """What a non-official install is about to put on the machine, in five lines."""
    quality = entry.get("quality") or {}
    runs = quality.get("runs") or {}
    independent = runs.get("independent") or {}
    fp = vinfo.get("fingerprint") or {}
    tested = " ".join(str(fp.get(k) or "*") for k in ("hardware", "os_version", "app_version")).strip() or "unknown"
    lines = [
        f"Install card: {key}@{version} ({trust}, tier {quality.get('tier') or 'draft'})",
        f"  has_python:   {'yes, runs Python on your machine' if vinfo.get('has_python') else 'no (YAML only)'}",
        f"  data_access:  {', '.join(vinfo.get('data_access') or []) or 'none declared'}",
        f"  side_effects: {', '.join(vinfo.get('side_effects') or []) or 'none declared'}"
        + ("  DESTRUCTIVE" if vinfo.get("destructive") else ""),
        f"  tos_risk:     {vinfo.get('tos_risk') or 'undeclared'}",
        f"  tested on:    {tested}; runs {runs.get('passed', 0)}/{runs.get('total', 0)} passed"
        f" ({independent.get('passed', 0)}/{independent.get('total', 0)} independent)",
    ]
    return "\n".join(lines)


def _ask_tty(prompt: str) -> bool:
    if not sys.stdin or not sys.stdin.isatty():
        return False
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _point_latest(skill_root: Path) -> str | None:
    """Point ``@latest`` at the highest installed version. Returns that version."""
    versions = [d.name for d in skill_root.iterdir() if d.is_dir() and (d / "skill.yaml").exists()]
    best = max_version(versions)
    link, txt = skill_root / "@latest", skill_root / "latest.txt"
    if link.is_symlink() or link.exists():
        link.unlink()
    if txt.exists():
        txt.unlink()
    if best is None:
        return None
    try:
        link.symlink_to(best, target_is_directory=True)
    except (OSError, NotImplementedError):
        txt.write_text(best + "\n")
    return best


def _read_meta(vdir: Path) -> dict:
    try:
        return json.loads((vdir / INSTALL_META).read_text())
    except (OSError, ValueError):
        return {}


def _installed_from_dir(author: str, slug: str, vdir: Path) -> InstalledSkill:
    meta = _read_meta(vdir)
    return InstalledSkill(
        author=author,
        slug=slug,
        version=vdir.name,
        path=vdir,
        trust=meta.get("trust", "unverified"),
        source=meta.get("source", ""),
        rev=meta.get("rev", ""),
        installed_at=meta.get("installed_at", ""),
        files=meta.get("files", {}),
    )


# ── public API ──────────────────────────────────────────────────────────────


def install(
    ref: str,
    *,
    source: str | None = None,
    force: bool = False,
    yes: bool = False,
    confirm: Callable[[str], bool] | None = None,
    registry: dict | None = None,
) -> InstalledSkill:
    """Install ``<author>/<slug>[@<version>]`` into ``$GHOST_SKILLS_DIR``.

    Args:
        ref: skill ref; ``@latest`` default, ``@main`` warns.
        source: optional base URL / local dir laid out like the hub repo. Anything
            other than the hub repo makes the install ``unverified``.
        force: reinstall over an existing version dir; also overrides quarantine.
        yes: accept the unverified prompt non-interactively (``--yes``).
        confirm: prompt callback for unverified installs (default: stdin y/N).
        registry: pre-fetched registry (skips the registry download).

    Raises:
        HubError: not in registry, download failure, sha256 mismatch, unsafe path.
        TrustDeclined: unverified install not confirmed, or quarantined without force.
    """
    r = parse_ref(ref)
    if r.version == MAIN:
        log.warning("installing %s@main: unpinned, tracks the hub's main branch", r.key)
    src = _normalize_source(source)
    if src is not None and _is_hub_source(src):
        src = None  # the hub repo itself: use the CDN path + tags
    reg = registry if registry is not None else fetch_registry(src)
    entry = reg["skills"].get(r.key)
    if not entry:
        raise HubError(f"{r.key} is not in the registry")
    if entry.get("schema") == "v1":
        raise HubError(
            f"{r.key} is a legacy v1 skill and cannot be installed from the hub. "
            "It still runs through the bundled v1 runtime in a source checkout; "
            f"maintainers can convert it with `ghost skill migrate skillhub/{r.author}/{r.slug}`."
        )
    versions = entry.get("versions") or {}
    version = r.version if r.pinned else entry.get("latest") or max_version(versions)
    if not version or version not in versions:
        avail = ", ".join(sorted(versions, key=version_key)) or "(none)"
        raise HubError(f"{r.key}@{r.version} not in registry; available: {avail}")
    if not is_semver(version) and version != MAIN:
        raise HubError(f"{r.key}: registry version {version!r} is not SemVer")
    vinfo = versions[version]
    files = vinfo.get("files") or {}
    if "skill.yaml" not in files:
        raise HubError(f"{r.key}@{version}: registry entry lists no skill.yaml")

    trust = entry.get("trust") or "unverified"
    if trust not in TRUST_TIERS:
        trust = "unverified"
    if not _is_hub_source(src) and trust != "quarantined":
        trust = "unverified"
    rev = _rev_for(r, version, vinfo)
    review_url = (src or f"https://github.com/{hub_repo()}/tree/{rev}") + f"/skillhub/{r.author}/{r.slug}"

    skills_dir = installed_skills_dir()
    skill_root = skills_dir / r.author / r.slug
    dest = skill_root / version
    if not dest.resolve().is_relative_to(skills_dir.resolve()):
        raise HubError(f"{r.key}@{version}: install path escapes the skills dir")
    if dest.exists() and not force:
        log.info("%s@%s already installed at %s", r.key, version, dest)
        return _installed_from_dir(r.author, r.slug, dest)

    first_install = not skill_root.is_dir()
    if trust != "official":
        print(install_card(r.key, version, entry, vinfo, trust), file=sys.stderr)
    _trust_gate(f"{r.key}@{version}", trust, url=review_url, yes=yes, force=force, confirm=confirm, author=r.author)
    if trust == "verified" and vinfo.get("has_python") and first_install and not yes:
        # Unverified installs were just asked; verified Python still needs one explicit yes the first time.
        if not (confirm or _ask_tty)("This community skill runs its own Python on your machine. Install? (y/N) "):
            raise TrustDeclined(
                f"first install of community skill {r.key}@{version} with Python needs --yes or a confirmation"
            )
    status = entry.get("status") or ("blocked" if (entry.get("flags") or {}).get("blocked") else "active")
    if status in STATUS_WARNINGS:
        print(STATUS_WARNINGS[status].format(ref=f"{r.key}@{version}"), file=sys.stderr)
    if vinfo.get("destructive"):
        effects = ", ".join(vinfo.get("side_effects") or []) or "unspecified"
        print(DESTRUCTIVE_WARNING.format(ref=f"{r.key}@{version}", effects=effects), file=sys.stderr)
        if not yes and not (confirm or _ask_tty)("Acknowledge and install? (y/N) "):
            raise TrustDeclined(f"install of destructive skill {r.key}@{version} not acknowledged")

    # Download + verify everything before touching the install dir.
    blobs = _download_verified(r, version, vinfo, files, rev=rev, source=src)

    skill_root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=skill_root))
    try:
        for rel, data in blobs.items():
            out = tmp.joinpath(*rel.parts)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
        meta = {
            "ref": f"{r.key}@{version}",
            "version": version,
            "trust": trust,
            "source": src or f"hub:{hub_repo()}",
            "rev": rev,
            "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "files": files,
        }
        (tmp / INSTALL_META).write_text(json.dumps(meta, indent=2) + "\n")
        if dest.exists():
            shutil.rmtree(dest)
        tmp.rename(dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    _point_latest(skill_root)
    return _installed_from_dir(r.author, r.slug, dest)


def uninstall(ref: str) -> list[Path]:
    """Remove an installed skill. Unpinned ref removes all versions. Returns removed dirs."""
    r = parse_ref(ref)
    skill_root = installed_skills_dir() / r.author / r.slug
    if not skill_root.is_dir():
        raise HubError(f"{r.key} is not installed")
    if not r.pinned:
        shutil.rmtree(skill_root)
        author_dir = skill_root.parent
        if author_dir.is_dir() and not any(author_dir.iterdir()):
            author_dir.rmdir()
        return [skill_root]
    vdir = skill_root / r.version
    if not vdir.is_dir():
        raise HubError(f"{r.key}@{r.version} is not installed")
    shutil.rmtree(vdir)
    if _point_latest(skill_root) is None:
        shutil.rmtree(skill_root)
    return [vdir]


def list_installed() -> list[InstalledSkill]:
    """Every installed ``<author>/<slug>/<version>``, sorted by key then version."""
    root = installed_skills_dir()
    out: list[InstalledSkill] = []
    if not root.is_dir():
        return out
    for author_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for slug_dir in sorted(p for p in author_dir.iterdir() if p.is_dir() and not p.is_symlink()):
            vdirs = [
                d
                for d in slug_dir.iterdir()
                if d.is_dir() and not d.is_symlink() and not d.name.startswith(".") and (d / "skill.yaml").exists()
            ]
            for vdir in sorted(vdirs, key=lambda d: version_key(d.name)):
                out.append(_installed_from_dir(author_dir.name, slug_dir.name, vdir))
    return out


def _installed_latest() -> dict[str, str]:
    best: dict[str, str] = {}
    for s in list_installed():
        cur = best.get(s.key)
        if cur is None or version_key(s.version) > version_key(cur):
            best[s.key] = s.version
    return best


def outdated(*, source: str | None = None, registry: dict | None = None) -> list[dict]:
    """Installed skills whose registry ``latest`` is newer: ``[{ref, installed, latest}]``."""
    installed = _installed_latest()
    if not installed:
        return []
    reg = registry if registry is not None else fetch_registry(source)
    out = []
    for key, have in sorted(installed.items()):
        latest = (reg["skills"].get(key) or {}).get("latest")
        if latest and version_key(latest) > version_key(have):
            out.append({"ref": key, "installed": have, "latest": latest})
    return out


def update(
    ref: str,
    *,
    source: str | None = None,
    yes: bool = False,
    confirm: Callable[[str], bool] | None = None,
    registry: dict | None = None,
) -> InstalledSkill | None:
    """Install the registry's latest when newer than the installed latest. None when up to date."""
    r = parse_ref(ref)
    reg = registry if registry is not None else fetch_registry(source)
    entry = reg["skills"].get(r.key)
    if not entry:
        raise HubError(f"{r.key} is not in the registry")
    latest = entry.get("latest")
    have = _installed_latest().get(r.key)
    if have and latest and version_key(latest) <= version_key(have):
        return None
    return install(f"{r.key}@{latest}" if latest else r.key, source=source, yes=yes, confirm=confirm, registry=reg)
