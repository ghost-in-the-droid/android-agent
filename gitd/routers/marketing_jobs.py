"""Marketing-jobs router — single seam for external marketing agents to
queue a TikTok post via Ghost's scheduler/job_queue.

Lives in the public gitd/ namespace so the external social-media-agent
(at ~/Agent/social-media-agent/) can call into Ghost without depending
on the premium plugin.

Safety: `action` is force-overridden to 'draft' regardless of input.
The agent has no permission to live-publish from this seam — that's a
separate design review. If callers pass action='publish' we log a
warning and still save as draft.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from gitd.models.base import get_db
from gitd.bots.common.device import is_ios_ref
from gitd.services._job_helpers import _enqueue_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/marketing-jobs", tags=["marketing-jobs"])


class EnqueueRequest(BaseModel):
    video_path: str = Field(..., description="Absolute path to the video file on this machine")
    caption: str = ""
    hashtags: str = ""
    phone_serial: str = Field(..., description="Android ADB serial of the phone to post from")
    tts_text: Optional[str] = None
    scheduled_at: Optional[str] = Field(None, description="ISO timestamp; informational only — runs ASAP")
    account: Optional[str] = Field(None, description="Expected active TikTok account on the phone")
    action: str = Field("draft", description="Forced to 'draft' regardless of input")


@router.post("/enqueue", summary="Enqueue a TikTok post job (draft only)")
def enqueue_marketing_job(req: EnqueueRequest, db: Session = Depends(get_db)):
    """Queue a TikTok post job for the scheduler to pick up.

    Wraps `_enqueue_job` with `job_type='post'`. Force-overrides action to
    'draft' so external marketing agents cannot live-publish through this
    seam. The existing `bots/tiktok/upload.py` worker picks it up next
    scheduler tick.
    """
    if not os.path.isabs(req.video_path):
        raise HTTPException(status_code=400, detail="video_path must be absolute")
    if not os.path.exists(req.video_path):
        raise HTTPException(status_code=400, detail=f"video_path does not exist: {req.video_path}")
    if not req.phone_serial:
        raise HTTPException(status_code=400, detail="phone_serial required")
    if is_ios_ref(req.phone_serial):
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error": "unsupported_platform",
                "platform": "ios",
                "message": "TikTok marketing post jobs are Android-only until the iOS TikTok workflow is ported",
            },
        )

    # Hard-force draft. If the caller asked for publish, log a warning so we
    # can see attempts in the log, but never honor it.
    if req.action and req.action.lower() != "draft":
        logger.warning(
            "marketing_jobs.enqueue: rejecting action=%r from external caller; saving as draft instead",
            req.action,
        )

    config = {
        "video": req.video_path,
        "caption": req.caption,
        "hashtags": req.hashtags,
        "action": "draft",
    }
    if req.tts_text:
        config["inject_tts"] = True
        config["tts_text"] = req.tts_text
    if req.account:
        config["account"] = req.account

    job_id = _enqueue_job(
        db,
        scheduled_job_id=None,
        phone_serial=req.phone_serial,
        job_type="post",
        priority=2,
        config_json=config,
        max_duration_s=1800,
        trigger="marketing_agent",
        status="pending",
    )

    return {
        "job_id": f"ghost-job-{job_id}",
        "estimated_post_at": req.scheduled_at,  # informational, not enforced
        "action": "draft",
        "phone_serial": req.phone_serial,
    }
