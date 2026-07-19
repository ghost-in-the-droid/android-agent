"""TikTok skill — upload videos, publish drafts, navigate the app."""

from pathlib import Path

from gitd.skills.base import Skill

_SKILL_DIR = Path(__file__).parent


def load() -> Skill:
    """Load the TikTok skill with public actions and workflows."""
    from gitd.skills.tiktok.actions import (
        DismissPopup,
        NavigateToProfile,
        OpenApp,
        TapSearch,
        TypeAndSearch,
    )
    from gitd.skills.tiktok.workflows.publish_draft import PublishDraft
    from gitd.skills.tiktok.workflows.upload_video import UploadVideo

    skill = Skill(_SKILL_DIR)
    for cls in [OpenApp, NavigateToProfile, TapSearch, TypeAndSearch, DismissPopup]:
        skill.register_action(cls)
    for cls in [UploadVideo, PublishDraft]:
        skill.register_workflow(cls)
    return skill
