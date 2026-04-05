"""Play Store workflows."""
from gitd.skills.base import Workflow, Action
from .actions.core import OpenStore, SearchApp, InstallApp


class InstallByName(Workflow):
    """Search for an app by name and install the first result."""
    name = 'install_by_name'
    description = 'Search Play Store by name and install the app'
    app_package = 'com.android.vending'

    def __init__(self, device, elements=None, query: str = '', **kw):
        super().__init__(device, elements)
        self.query = query

    def steps(self) -> list[Action]:
        return [
            SearchApp(self.device, query=self.query),
            # After search, the first result is usually the right app
            # InstallApp needs the package — but from search we tap the first result
            # which opens the store page, then we tap Install
            _TapFirstResult(self.device),
        ]


class _TapFirstResult(Action):
    """Tap the first app result in Play Store search results, then tap Install."""
    name = 'tap_first_result'
    description = 'Tap first search result and install'
    max_retries = 2

    def execute(self):
        import time
        from gitd.skills.base import ActionResult
        xml = self.device.dump_xml()
        # Find the first clickable element that looks like an app listing
        # Play Store results have app names as clickable text
        for node in self.device.nodes(xml):
            if 'clickable="true"' not in node:
                continue
            text = self.device.node_text(node)
            # Skip nav elements
            if text in ('', 'Search', 'Games', 'Apps', 'Books', 'Movies'):
                continue
            b = self.device.node_bounds(node)
            if not b:
                continue
            # Skip small elements (icons, buttons)
            w = b[2] - b[0]
            if w < 200:
                continue
            cx, cy = self.device.node_center(b)
            self.device.tap(cx, cy)
            time.sleep(3)
            # Now on app page — find Install button
            xml2 = self.device.dump_xml()
            for n2 in self.device.nodes(xml2):
                txt = self.device.node_text(n2)
                if txt == 'Install':
                    b2 = self.device.node_bounds(n2)
                    if b2:
                        cx2, cy2 = self.device.node_center(b2)
                        self.device.tap(cx2, cy2, delay=2.0)
                        return ActionResult(success=True, data={'status': 'installing', 'app': text})
                if txt in ('Open', 'Play'):
                    return ActionResult(success=True, data={'status': 'already_installed', 'app': text})
            return ActionResult(success=False, error='Install button not found on app page')
        return ActionResult(success=False, error='No app results found in search')
