"""Google Maps skill — search places, fetch directions with ETA and distance."""
from pathlib import Path

from gitd.skills.base import Skill

_SKILL_DIR = Path(__file__).parent


def load() -> Skill:
    """Load the Google Maps skill with public actions and workflows."""
    from gitd.skills.google_maps.actions import (
        OpenApp, SearchPlace, OpenDirections, SelectTravelMode,
        ReadRouteSummary, CloseCard,
    )
    from gitd.skills.google_maps.workflows import GetDirections

    skill = Skill(_SKILL_DIR)
    for cls in [OpenApp, SearchPlace, OpenDirections, SelectTravelMode,
                ReadRouteSummary, CloseCard]:
        skill.register_action(cls)
    skill.register_workflow(GetDirections)
    return skill
