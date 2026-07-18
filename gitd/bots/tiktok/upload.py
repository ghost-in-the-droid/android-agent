"""Compatibility shim — re-export TikTok upload helpers from premium.

The actual implementation lives at internal/ghost_premium/bots/tiktok/upload.py.
This shim exists so scripts that import from gitd.bots.tiktok.upload (the
pre-split path) keep working after the public/premium split, without each
script needing to fall back manually.

If premium isn't installed, importing this module raises a clear ImportError
instead of pretending things work.
"""

try:
    from ghost_premium.bots.tiktok.upload import *  # noqa: F401, F403
except ImportError as e:
    raise ImportError(
        "gitd.bots.tiktok.upload requires the premium plugin to be installed. "
        "If you have premium, ensure internal/ghost_premium is on PYTHONPATH."
    ) from e
