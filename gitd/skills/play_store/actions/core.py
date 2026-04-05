"""Play Store actions — atomic operations for app management."""
import re
import time

from gitd.skills.base import Action, ActionResult

PLAY_PKG = "com.android.vending"


class OpenStore(Action):
    """Open the Google Play Store app."""
    name = 'open_store'
    description = 'Launch Google Play Store'
    max_retries = 1

    def execute(self) -> ActionResult:
        self.device.adb('shell', 'am', 'force-stop', PLAY_PKG)
        time.sleep(0.5)
        self.device.adb('shell', 'monkey', '-p', PLAY_PKG,
                        '-c', 'android.intent.category.LAUNCHER', '1')
        time.sleep(3)
        return ActionResult(success=True)


class SearchApp(Action):
    """Search for an app in Play Store."""
    name = 'search_app'
    description = 'Search Play Store for an app by name'
    max_retries = 2

    def __init__(self, device, elements=None, query: str = '', **kw):
        super().__init__(device, elements)
        self.query = query

    def execute(self) -> ActionResult:
        # Open Play Store search
        self.device.adb('shell', 'am', 'start', '-a', 'android.intent.action.VIEW',
                        '-d', f'market://search?q={self.query}')
        time.sleep(4)
        return ActionResult(success=True, data={'query': self.query})


class InstallApp(Action):
    """Install an app from Play Store by package name."""
    name = 'install_app'
    description = 'Install app from Play Store (opens store page, taps Install)'
    max_retries = 1

    def __init__(self, device, elements=None, package: str = '', **kw):
        super().__init__(device, elements)
        self.package = package

    def execute(self) -> ActionResult:
        # Open Play Store page for this package
        self.device.adb('shell', 'am', 'start', '-a', 'android.intent.action.VIEW',
                        '-d', f'market://details?id={self.package}')
        time.sleep(4)

        xml = self.device.dump_xml()
        # Check if already installed
        for node in self.device.nodes(xml):
            txt = self.device.node_text(node)
            if txt in ('Open', 'Play'):
                return ActionResult(success=True, data={'status': 'already_installed', 'package': self.package})

        # Find Install button
        for node in self.device.nodes(xml):
            txt = self.device.node_text(node)
            if txt == 'Install':
                b = self.device.node_bounds(node)
                if b:
                    cx, cy = self.device.node_center(b)
                    self.device.tap(cx, cy, delay=2.0)
                    # Wait for install to complete (poll for Open button)
                    for _ in range(60):
                        time.sleep(5)
                        xml2 = self.device.dump_xml()
                        for n2 in self.device.nodes(xml2):
                            if self.device.node_text(n2) == 'Open':
                                ver = self.device.get_app_version(self.package)
                                return ActionResult(success=True,
                                                    data={'status': 'installed', 'version': ver, 'package': self.package})
                    return ActionResult(success=False, error='Install timed out (5 min)')

        return ActionResult(success=False, error=f'Install button not found for {self.package}')


class UninstallApp(Action):
    """Uninstall an app via ADB."""
    name = 'uninstall_app'
    description = 'Uninstall an app from the device'
    max_retries = 1

    def __init__(self, device, elements=None, package: str = '', **kw):
        super().__init__(device, elements)
        self.package = package

    def execute(self) -> ActionResult:
        try:
            out = self.device.adb('shell', 'pm', 'uninstall', self.package, timeout=30)
            success = 'success' in out.lower()
            return ActionResult(success=success,
                                data={'status': 'uninstalled' if success else 'failed', 'output': out.strip()})
        except Exception as e:
            return ActionResult(success=False, error=str(e))


class UpdateApp(Action):
    """Update an app via Play Store."""
    name = 'update_app'
    description = 'Update app to latest version via Play Store'
    max_retries = 1

    def __init__(self, device, elements=None, package: str = '', **kw):
        super().__init__(device, elements)
        self.package = package

    def execute(self) -> ActionResult:
        try:
            new_ver = self.device.update_app(self.package)
            return ActionResult(success=True, data={'version': new_ver, 'package': self.package})
        except RuntimeError as e:
            return ActionResult(success=False, error=str(e))


class CheckVersion(Action):
    """Check installed version of an app."""
    name = 'check_version'
    description = 'Get the installed version of an app'
    max_retries = 1

    def __init__(self, device, elements=None, package: str = '', **kw):
        super().__init__(device, elements)
        self.package = package

    def execute(self) -> ActionResult:
        ver = self.device.get_app_version(self.package)
        installed = ver and ver != 'unknown'
        return ActionResult(success=True,
                            data={'package': self.package, 'installed': installed, 'version': ver if installed else 'not installed'})
