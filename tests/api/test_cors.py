"""CORS policy regression tests — see CWE-352 fix.

The API exposes sensitive tools (ADB, skill install, file I/O). A wildcard
CORS allowlist paired with `allow_credentials=True` lets any web page the
developer visits issue credentialed requests to the API. Guard against
regressions by asserting the middleware only trusts the local dashboard/docs
origins.
"""
from fastapi.testclient import TestClient

from gitd.app import app


def test_cors_rejects_arbitrary_origin():
    with TestClient(app) as c:
        r = c.options(
            "/api/health",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        acao = r.headers.get("access-control-allow-origin", "")
        assert acao != "https://evil.example", (
            "CORS must not echo arbitrary Origin — see CWE-352 fix in gitd/app.py"
        )
        assert acao != "*", "wildcard ACAO with credentials is unsafe"


def test_cors_allows_frontend_dev_origin():
    with TestClient(app) as c:
        r = c.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:6175",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert r.headers.get("access-control-allow-origin") == "http://localhost:6175"
