"""Best-effort, opt-in transport for categorical run outcomes only."""
import ipaddress
import re
import json
import os
import sys
import uuid
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

from gitd.ghostcli.config import load_config


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send_run(skill, result, fingerprint, *, simulated=False):
    try:
        preferences = load_config().get('telemetry', {})
        endpoint = os.environ.get('GHOST_TELEMETRY_ENDPOINT', '')
        if preferences.get('enabled') is not True or os.environ.get('DO_NOT_TRACK', '').strip() == '1' or not endpoint:
            return
        identifier = preferences.get('install_id', '')
        parsed_id = uuid.UUID(identifier)
        if parsed_id.version != 4 or str(parsed_id) != identifier:
            return
        url = urlparse(endpoint)
        if url.username or url.password or url.fragment or url.query:
            return
        if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname == '127.0.0.1'):
            return
        skill_id = f'{skill.author}/{skill.name}'
        version = fingerprint['app_version']
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}/[a-z0-9][a-z0-9_-]{0,63}', skill_id):
            return
        if not re.fullmatch(r'[0-9][0-9A-Za-z.+_-]{0,63}', version) or fingerprint['os'] not in ('android', 'ios'):
            return
        try:
            ipaddress.ip_address(version)
        except ValueError:
            pass
        else:
            return
        payload = {'schema_version': 1, 'skill': f'{skill.author}/{skill.name}',
                   'app_version': fingerprint['app_version'], 'outcome': 'passed' if result.success else 'failed',
                   'os': fingerprint['os'], 'backend': 'fake' if simulated else 'device', 'install_id': identifier}
        encoded = json.dumps(payload, sort_keys=True)
        if os.environ.get('GHOST_TELEMETRY_DEBUG') == '1':
            print('Telemetry debug: ' + encoded)
            return
        request = Request(endpoint, data=encoded.encode(), headers={'Content-Type': 'application/json'}, method='POST')
        with build_opener(NoRedirect()).open(request, timeout=2) as response:
            response.read(1024)
    except Exception:
        # Telemetry cannot turn a completed local run into a CLI failure.
        print('Telemetry delivery skipped.', file=sys.stderr)
