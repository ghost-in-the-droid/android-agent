"""Skills routes: list, detail, run workflow/action, create, delete, update, export, registry."""

import io
import json
import re
import shutil
import time
import zipfile
from pathlib import Path

import requests as http_requests
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from gitd.models.base import get_db
from gitd.services.admin_auth import require_admin_token
from gitd.services.skill_creation import create_recorded_skill
from gitd.skills.platforms import (
    skill_android_package,
    skill_ios_bundle_id,
    skill_platform_error,
    skill_platforms,
    skill_supports_device,
    skill_supports_platform,
)

router = APIRouter(prefix="/api/skills", tags=["skills"])

# ── Registry cache (5 min TTL) ───────────────────────────────────────────
_REGISTRY_URL = "https://raw.githubusercontent.com/ghost-in-the-droid/android-agent/main/registry/index.json"
_COMMUNITY_URL = "https://raw.githubusercontent.com/ghost-in-the-droid/android-agent/main/registry/community.json"
_cache: dict[str, tuple[float, list]] = {}  # key -> (timestamp, data)
_CACHE_TTL = 300  # 5 minutes


def _fetch_cached(url: str, cache_key: str) -> list:
    """Fetch a JSON URL with 5-minute caching."""
    now = time.time()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return data
    try:
        resp = http_requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        _cache[cache_key] = (now, data)
        return data
    except Exception:
        # Return stale cache if available
        if cache_key in _cache:
            return _cache[cache_key][1]
        return []


_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _load_all_skills() -> dict:
    """Load all installed skills from gitd/skills/."""
    results = {}
    for d in sorted(_SKILLS_DIR.iterdir()):
        if d.is_dir() and (d / "skill.yaml").exists() and not d.name.startswith("__"):
            try:
                import yaml

                meta = yaml.safe_load((d / "skill.yaml").read_text()) or {}
                elements = {}
                if (d / "elements.yaml").exists():
                    elements = yaml.safe_load((d / "elements.yaml").read_text()) or {}
                popups = meta.get("popup_detectors", [])
                elements_ios = {}
                if (d / "elements_ios.yaml").exists():
                    elements_ios = yaml.safe_load((d / "elements_ios.yaml").read_text()) or {}
                platforms = skill_platforms(meta)
                results[d.name] = {
                    "name": meta.get("name", d.name),
                    "description": meta.get("description", ""),
                    "version": meta.get("version", "0.0.0"),
                    "kind": meta.get("kind", "hard"),
                    "has_guidance": (d / "guidance.md").exists(),
                    "app_package": meta.get("app_package", ""),
                    "android_package": skill_android_package(meta),
                    "ios_bundle_id": skill_ios_bundle_id(meta),
                    "platforms": platforms,
                    "supports_android": skill_supports_platform(meta, "android"),
                    "supports_ios": skill_supports_platform(meta, "ios"),
                    "platform_limitations": meta.get("platform_limitations", {}) or {},
                    "dir": d.name,
                    "elements_count": len(elements),
                    "elements_ios_count": len(elements_ios),
                    "popup_count": len(popups),
                    "popup_detectors": popups,
                    "metadata": meta,
                    "default_params": meta.get("default_params", {}),
                }
            except Exception as e:
                results[d.name] = {"name": d.name, "error": str(e)}
    return results


def _load_skill(name: str):
    """Dynamically load a skill by name."""
    import importlib

    try:
        mod = importlib.import_module(f"gitd.skills.{name}")
        if hasattr(mod, "load"):
            return mod.load()
    except Exception:
        pass
    rec_path = _SKILLS_DIR / name / "workflows" / "recorded.json"
    if rec_path.exists():
        steps = json.loads(rec_path.read_text())
        return {"_recorded": True, "steps": steps, "name": name}
    return None


@router.get("", summary="List All Installed Skills")
def api_skills_list(device: str = ""):
    """List all installed skills. Optional ?device=<ref> adds supported_on_device flag."""
    skills = _load_all_skills()
    for name, info in skills.items():
        if device:
            info["supported_on_device"] = skill_supports_device(info.get("metadata", {}), device)
        try:
            s = _load_skill(name)
            if s is None:
                info["actions"] = []
                info["workflows"] = []
            elif isinstance(s, dict) and s.get("_recorded"):
                info["actions"] = [
                    {"name": f"step_{i + 1}", "description": st.get("description", st.get("action", ""))}
                    for i, st in enumerate(s["steps"])
                ]
                info["workflows"] = [{"name": "recorded", "description": f"Replay {len(s['steps'])} recorded steps"}]
            else:
                info["actions"] = s.list_actions()
                info["workflows"] = s.list_workflows()
        except Exception as e:
            info["actions"] = []
            info["workflows"] = []
            info["load_error"] = str(e)
    return list(skills.values())


# ── Registry / Hub endpoints (MUST be before /{name}) ─────────────────


@router.get("/registry", summary="Fetch Official Skill Registry")
def api_skills_registry():
    """Fetch index.json from the official GitHub skill registry (cached 5 min)."""
    return _fetch_cached(_REGISTRY_URL, "registry")


@router.get("/community", summary="Fetch Community Skill Registry")
def api_skills_community():
    """Fetch community.json from GitHub (cached 5 min)."""
    return _fetch_cached(_COMMUNITY_URL, "community")


# Strict shape check for GitHub repo references.  ``_is_github_url`` only
# checks the prefix, which lets whitespace / newline / leading-dash tricks
# reach ``git clone`` as smuggled flags (e.g. ``--upload-pack=<cmd>``).
# Only accept plain ``[https://]github.com/<owner>/<repo>[.git]``.
_SAFE_GITHUB_URL_RE = re.compile(r"^(?:https?://)?github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+(?:\.git)?/?$")

# Registry names are drawn from ``_download_skill_from_registry`` output —
# keep the accepted alphabet narrow so the value can never do anything
# surprising when it eventually reaches ``importlib.import_module``.
_SAFE_REGISTRY_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]{0,63}$")


@router.post(
    "/install",
    summary="Install Skill From Registry or URL",
    dependencies=[Depends(require_admin_token)],
)
def api_skills_install(data: dict = Body(...)):
    """Install a skill by name (from registry) or by URL (GitHub repo).

    Body: {"name": "tiktok"} or {"url": "github.com/user/repo"}

    Requires the admin token dependency: installing a skill drops Python
    code into ``gitd/skills/<name>`` which is later loaded via
    ``importlib.import_module`` — trivially RCE for an unauthenticated
    caller (CWE-94).  See ``gitd/services/admin_auth.py``.
    """
    from gitd.cli import (
        _clone_github_skill,
        _download_skill_from_registry,
        _install_to_skills_dir,
        _validate_skill_dir,
    )

    name = data.get("name", "").strip() if isinstance(data.get("name"), str) else ""
    url = data.get("url", "").strip() if isinstance(data.get("url"), str) else ""

    if not name and not url:
        raise HTTPException(status_code=400, detail="Provide 'name' or 'url'")

    if url:
        # Reject anything that isn't a plain github.com/<owner>/<repo> URL —
        # ``git clone`` will happily interpret ``-uexec=...`` style tokens
        # as flags when we haven't sanitised them first.
        if not _SAFE_GITHUB_URL_RE.match(url):
            raise HTTPException(
                status_code=400,
                detail=("url must look like 'github.com/<owner>/<repo>' (no shell metacharacters, no leading dash)."),
            )
        source = _clone_github_skill(url)
        if source is None:
            raise HTTPException(status_code=400, detail=f"Failed to clone {url}")
        try:
            if not _validate_skill_dir(source, verbose=False):
                raise HTTPException(
                    status_code=400,
                    detail=("Skill failed validation (see server logs); refusing to install untrusted code."),
                )
            ok = _install_to_skills_dir(source)
        finally:
            shutil.rmtree(source, ignore_errors=True)
        if not ok:
            raise HTTPException(status_code=500, detail="Install failed")
        return {"ok": True, "message": f"Installed from {url}"}

    if name:
        if not _SAFE_REGISTRY_NAME_RE.match(name):
            raise HTTPException(status_code=400, detail="Invalid registry name")
        source = _download_skill_from_registry(name)
        if source is None:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found in registry")
        try:
            if not _validate_skill_dir(source, verbose=False):
                raise HTTPException(
                    status_code=400,
                    detail=("Skill failed validation (see server logs); refusing to install untrusted code."),
                )
            ok = _install_to_skills_dir(source, name=name)
        finally:
            shutil.rmtree(source, ignore_errors=True)
        if not ok:
            raise HTTPException(status_code=500, detail="Install failed")
        return {"ok": True, "message": f"Installed '{name}' from registry"}

    raise HTTPException(status_code=400, detail="Provide a valid 'name' or GitHub 'url'")


# ── Skill compatibility / execution tracking (MUST be before /{name}) ──


@router.get("/compat", summary="Get Skill Compatibility Matrix")
def api_skill_compat(device: str = "", db: Session = Depends(get_db)):
    """Get skill compatibility matrix. Optionally filter by device."""
    from gitd.models.skill_compat import SkillCompat

    q = db.query(SkillCompat)
    if device:
        q = q.filter(SkillCompat.device_serial == device)
    rows = q.order_by(SkillCompat.skill_name, SkillCompat.target_name).all()
    return [
        {
            "device_serial": r.device_serial,
            "skill_name": r.skill_name,
            "target_type": r.target_type,
            "target_name": r.target_name,
            "app_version": r.app_version,
            "status": r.status,
            "last_run_at": r.last_run_at,
            "last_error": r.last_error,
            "run_count": r.run_count,
            "ok_count": r.ok_count,
            "fail_count": r.fail_count,
        }
        for r in rows
    ]


@router.get("/runs", summary="List Skill Execution History")
def api_skill_runs(device: str = "", skill: str = "", limit: int = 50, db: Session = Depends(get_db)):
    """Get recent skill execution history."""
    from gitd.models.skill_compat import SkillRun

    q = db.query(SkillRun)
    if device:
        q = q.filter(SkillRun.device_serial == device)
    if skill:
        q = q.filter(SkillRun.skill_name == skill)
    rows = q.order_by(SkillRun.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "device_serial": r.device_serial,
            "skill_name": r.skill_name,
            "target_type": r.target_type,
            "target_name": r.target_name,
            "app_version": r.app_version,
            "status": r.status,
            "duration_ms": r.duration_ms,
            "error_msg": r.error_msg,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "is_verify": bool(r.is_verify),
        }
        for r in rows
    ]


@router.get("/{name}", summary="Get Skill Detail")
def api_skill_detail(name: str):
    """Skill detail."""
    skills = _load_all_skills()
    if name not in skills:
        raise HTTPException(status_code=404, detail=f'Skill "{name}" not found')
    info = skills[name]
    try:
        s = _load_skill(name)
        if s is None:
            pass
        elif isinstance(s, dict) and s.get("_recorded"):
            info["actions"] = [
                {"name": f"step_{i + 1}", "description": st.get("description", st.get("action", ""))}
                for i, st in enumerate(s["steps"])
            ]
            info["workflows"] = [{"name": "recorded", "description": f"Replay {len(s['steps'])} recorded steps"}]
            info["recorded_steps"] = s["steps"]
        else:
            info["actions"] = [
                {"name": a, "description": getattr(s._actions.get(a), "description", "")} for a in s.list_actions()
            ]
            info["workflows"] = [
                {"name": w, "description": getattr(s._workflows.get(w), "description", "")} for w in s.list_workflows()
            ]
        import yaml

        elem_path = _SKILLS_DIR / name / "elements.yaml"
        if elem_path.exists():
            info["elements"] = yaml.safe_load(elem_path.read_text()) or {}
        # Soft skills carry markdown guidance instead of actions/workflows.
        guidance_path = _SKILLS_DIR / name / "guidance.md"
        if guidance_path.exists():
            info["guidance"] = guidance_path.read_text()
    except Exception as e:
        info["load_error"] = str(e)
    return info


@router.get("/{name}/actions", summary="List Skill Actions")
def api_skill_actions(name: str):
    """List actions for a skill."""
    try:
        s = _load_skill(name)
        if s is None:
            return []
        if isinstance(s, dict) and s.get("_recorded"):
            return [
                {"name": f"step_{i + 1}", "description": st.get("description", st.get("action", ""))}
                for i, st in enumerate(s["steps"])
            ]
        return [{"name": a, "description": getattr(s._actions.get(a), "description", "")} for a in s.list_actions()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}/workflows", summary="List Skill Workflows")
def api_skill_workflows(name: str):
    """List workflows for a skill."""
    try:
        s = _load_skill(name)
        if s is None:
            return []
        if isinstance(s, dict) and s.get("_recorded"):
            return [{"name": "recorded", "description": f"Replay {len(s['steps'])} recorded steps"}]
        return [{"name": w, "description": getattr(s._workflows.get(w), "description", "")} for w in s.list_workflows()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{name}/run", summary="Run Skill Workflow")
def api_skill_run(name: str, data: dict = Body({})):
    """Run a workflow via the job queue."""
    workflow_name = data.get("workflow", "")
    params = data.get("params", {})
    device_serial = data.get("device", "")
    if not workflow_name:
        raise HTTPException(status_code=400, detail="workflow name required")
    if not device_serial:
        raise HTTPException(status_code=400, detail="device serial required")

    skills = _load_all_skills()
    info = skills.get(name)
    if info and not skill_supports_device(info.get("metadata", {}), device_serial):
        raise HTTPException(status_code=400, detail=skill_platform_error(name, info.get("metadata", {}), device_serial))

    from gitd.models import SessionLocal
    from gitd.services.db_helpers import enqueue_job

    session = SessionLocal()
    try:
        job_id = enqueue_job(
            session,
            phone_serial=device_serial,
            job_type="skill_workflow",
            priority=2,
            config_json={"skill": name, "workflow": workflow_name, "params": params},
            trigger="api",
        )
    finally:
        session.close()
    return {"ok": True, "job_id": job_id, "message": f"Enqueued workflow {name}/{workflow_name} on {device_serial}"}


@router.post("/{name}/run-action", summary="Run Skill Action")
def api_skill_run_action(name: str, data: dict = Body({})):
    """Run an individual action via the job queue."""
    action_name = data.get("action", "")
    params = data.get("params", {})
    device_serial = data.get("device", "")
    if not action_name:
        raise HTTPException(status_code=400, detail="action name required")
    if not device_serial:
        raise HTTPException(status_code=400, detail="device serial required")

    from gitd.models import SessionLocal
    from gitd.services.db_helpers import enqueue_job

    session = SessionLocal()
    try:
        job_id = enqueue_job(
            session,
            phone_serial=device_serial,
            job_type="skill_action",
            priority=2,
            config_json={"skill": name, "action": action_name, "params": params},
            trigger="api",
        )
    finally:
        session.close()
    return {"ok": True, "job_id": job_id, "message": f"Enqueued action {name}/{action_name} on {device_serial}"}


@router.post("/{name}/verify", summary="Verify Skill On Device")
def api_skill_verify(name: str, data: dict = Body({})):
    """Run a skill workflow/action as a verification test (synchronous, not queued).
    Marks the execution with is_verify=1 for tracking."""
    workflow_name = data.get("workflow", "")
    action_name = data.get("action", "")
    params = data.get("params", {})
    device_serial = data.get("device", "")
    if not device_serial:
        raise HTTPException(status_code=400, detail="device serial required")
    if not workflow_name and not action_name:
        raise HTTPException(status_code=400, detail="workflow or action name required")

    import subprocess

    runner = Path(__file__).resolve().parent.parent / "skills" / "_run_skill.py"
    cmd = [
        "python3",
        "-u",
        str(runner),
        "--skill",
        name,
        "--device",
        device_serial,
        "--params",
        json.dumps(params),
        "--verify",
    ]
    if workflow_name:
        cmd.extend(["--workflow", workflow_name])
    else:
        cmd.extend(["--action", action_name])

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120, cwd=str(Path(__file__).resolve().parent.parent.parent)
    )
    output = result.stdout.strip()
    if result.returncode != 0:
        output += f"\nSTDERR: {result.stderr.strip()}" if result.stderr else ""
        return {"ok": False, "output": output, "exit_code": result.returncode}
    return {"ok": True, "output": output}


@router.delete("/compat/{device}/{skill_name}", summary="Reset Skill Compatibility")
def api_skill_compat_reset(device: str, skill_name: str, db: Session = Depends(get_db)):
    """Reset compatibility status for a skill on a device (re-test)."""
    from gitd.models.skill_compat import SkillCompat

    db.query(SkillCompat).filter_by(device_serial=device, skill_name=skill_name).delete()
    db.commit()
    return {"ok": True, "message": f"Reset compat for {skill_name} on {device}"}


@router.post("/create-from-recording", summary="Create Skill From Recording")
def api_skills_create_from_recording(data: dict = Body({})):
    """Create a skill from recorded steps. Platform-aware — see create_recorded_skill."""
    name = data.get("name", "new_skill").strip().lower().replace(" ", "_")
    steps = data.get("steps", [])
    if not name or not steps:
        raise HTTPException(status_code=400, detail="name and steps required")
    try:
        return create_recorded_skill(
            name=name,
            steps=steps,
            app_package=data.get("app_package", ""),
            android_package=data.get("android_package"),
            platforms=data.get("platforms", ""),
            ios_bundle_id=data.get("ios_bundle_id", ""),
            elements_ios=data.get("elements_ios"),
            elements_android=data.get("elements_android"),
            skills_dir=_SKILLS_DIR,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/draft-from-chat", summary="Draft Recorded Steps From A Chat")
def api_skills_draft_from_chat(data: dict = Body({})):
    """Distil a chat conversation's action trace into draft recorded steps (no write).

    The 'draft' half of draft -> review -> commit: the caller (LLM or UI) reviews
    and revises the returned steps, then POSTs them to /save-from-chat.
    """
    conversation_id = (data.get("conversation_id") or "").strip()
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id required")
    from gitd.services.skills_from_chat import draft_hard_skill

    try:
        return draft_hard_skill(conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/save-from-chat", summary="Save A Skill From A Chat")
def api_skills_save_from_chat(data: dict = Body({})):
    """Commit a HARD or SOFT skill from a chat conversation.

    HARD: pass revised `steps` (from /draft-from-chat) or just a `conversation_id`
    to re-distil. SOFT: pass `guidance` markdown.
    """
    name = (data.get("name") or "").strip().lower().replace(" ", "_")
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    from gitd.services.skills_from_chat import commit_skill

    try:
        return commit_skill(
            kind=data.get("kind", "hard"),
            name=name,
            app_package=data.get("app_package", ""),
            description=data.get("description", ""),
            steps=data.get("steps"),
            guidance=data.get("guidance"),
            conversation_id=data.get("conversation_id"),
            skills_dir=_SKILLS_DIR,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{name}", summary="Delete Custom Skill")
def api_skill_delete(name: str):
    """Delete a custom skill."""
    if name in ("_base", "tiktok", "instagram"):
        raise HTTPException(status_code=400, detail="Cannot delete built-in skills")
    skill_dir = _SKILLS_DIR / name
    if not skill_dir.exists():
        raise HTTPException(status_code=404, detail=f'Skill "{name}" not found')
    shutil.rmtree(skill_dir)
    return {"ok": True}


@router.put("/{name}/update", summary="Update Skill Metadata And Steps")
def api_skill_update(name: str, data: dict = Body({})):
    """Update a recorded skill's steps and metadata."""
    skill_dir = _SKILLS_DIR / name
    if not skill_dir.exists() or not (skill_dir / "skill.yaml").exists():
        raise HTTPException(status_code=404, detail=f'Skill "{name}" not found')

    import yaml

    meta_path = skill_dir / "skill.yaml"
    meta = yaml.safe_load(meta_path.read_text()) or {}
    if data.get("name"):
        meta["name"] = data["name"]
    if data.get("description"):
        meta["description"] = data["description"]
    if data.get("app_package"):
        meta["app_package"] = data["app_package"]
    meta_path.write_text(yaml.dump(meta, default_flow_style=False))

    if data.get("steps"):
        rec_dir = skill_dir / "workflows"
        rec_dir.mkdir(exist_ok=True)
        (rec_dir / "recorded.json").write_text(json.dumps(data["steps"], indent=2))

    return {"ok": True, "steps": len(data.get("steps", []))}


@router.get("/export/{name}", summary="Export Skill As ZIP")
def api_skill_export(name: str):
    """Download skill as ZIP."""
    skill_dir = _SKILLS_DIR / name
    if not skill_dir.exists() or not (skill_dir / "skill.yaml").exists():
        raise HTTPException(status_code=404, detail=f'Skill "{name}" not found')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in skill_dir.rglob("*"):
            if f.is_file() and "__pycache__" not in str(f):
                zf.write(f, f.relative_to(skill_dir.parent))
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={name}_skill.zip"},
    )
