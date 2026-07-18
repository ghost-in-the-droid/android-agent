"""Admin-token authentication for privileged endpoints.

The FastAPI server binds to ``0.0.0.0:5055`` by default and, historically,
had no authentication at all. That was fine for the "single developer with
their phone on their desk" use case but became a real problem for endpoints
that let the caller install code / execute processes on the operator's
machine — most notably ``POST /api/skills/install`` (CWE-94: attacker URL
→ ``git clone`` → subsequent ``importlib.import_module`` = RCE).

This module provides a tiny FastAPI ``Depends`` guard that:

  * Reads the shared secret from ``GITD_ADMIN_TOKEN`` at request time
    (so tests / operators can flip it without restarting the process).
  * Accepts the token via either the ``X-Ghost-Admin-Token`` header or
    ``Authorization: Bearer <token>`` (whichever the caller prefers).
  * Uses ``hmac.compare_digest`` for constant-time comparison.
  * Refuses the request when the env var is unset — the previous
    "reachable from anywhere by default" posture must not be silently
    restored by simply not configuring the token.

Operators who genuinely need the old zero-auth behaviour (e.g. isolated
CI containers) can opt in with ``GITD_ALLOW_UNAUTHENTICATED_ADMIN=1``.
It is deliberately noisy so it does not sneak into production.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

_ENV_TOKEN = "GITD_ADMIN_TOKEN"
_ENV_ALLOW_UNAUTH = "GITD_ALLOW_UNAUTHENTICATED_ADMIN"
_HEADER = "X-Ghost-Admin-Token"


def _extract_bearer(authorization: str | None) -> str | None:
    """Return the token part of an ``Authorization: Bearer <token>`` header."""
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def require_admin_token(
    x_ghost_admin_token: str | None = Header(default=None, alias=_HEADER),
    authorization: str | None = Header(default=None),
) -> None:
    """FastAPI dependency: enforce a valid admin token.

    Raises ``HTTPException(401)`` when the caller cannot prove possession
    of the shared secret, or ``HTTPException(500)`` when the operator has
    left the endpoint unconfigured on a network-reachable server.
    """
    if os.environ.get(_ENV_ALLOW_UNAUTH) == "1":
        # Explicit opt-in for isolated environments only.
        logger.warning(
            "admin auth bypassed via %s=1 — do not use on shared hosts",
            _ENV_ALLOW_UNAUTH,
        )
        return

    expected = os.environ.get(_ENV_TOKEN, "").strip()
    if not expected:
        # Fail closed. The previous default was "reachable from any origin
        # the network can route to us", which is what enabled the RCE.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Admin endpoints are disabled: set the GITD_ADMIN_TOKEN "
                "environment variable to a strong random secret and send "
                "it in the X-Ghost-Admin-Token header (or as "
                "'Authorization: Bearer <token>')."
            ),
        )

    supplied = (x_ghost_admin_token or "").strip() or _extract_bearer(authorization) or ""
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token.",
        )
