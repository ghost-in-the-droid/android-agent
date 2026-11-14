"""Get directions workflow — search a destination, read ETA/distance per mode."""
from gitd.skills.base import Workflow, Action, EngineConfig

from gitd.skills.google_maps.actions.core import (
    SearchPlace, OpenDirections, SelectTravelMode, ReadRouteSummary,
)


class GetDirections(Workflow):
    name = "get_directions"
    description = "Search a destination and return route summary (ETA, distance, per-mode times)"
    # The global popup list treats any content-desc="Close" as a dismissible
    # dialog — Maps place cards always have a Close header button, so popup
    # detection closes the card mid-flow. Opt out entirely.
    engine = EngineConfig(skip_popup_detect=True)

    def __init__(self, device, elements=None, *, destination: str = "",
                 mode: str = "driving", **kwargs):
        super().__init__(device, elements)
        self.destination = destination
        self.mode = mode

    def steps(self) -> list[Action]:
        return [
            SearchPlace(self.device, self.elements, query=self.destination),
            OpenDirections(self.device, self.elements),
            SelectTravelMode(self.device, self.elements, mode=self.mode),
            ReadRouteSummary(self.device, self.elements, mode=self.mode),
        ]
