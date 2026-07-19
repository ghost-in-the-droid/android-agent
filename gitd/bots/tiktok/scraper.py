"""Compatibility shim — re-export TikTok scraper helpers from premium."""

try:
    from ghost_premium.bots.tiktok.scraper import *  # noqa: F401, F403
except ImportError as e:
    raise ImportError("gitd.bots.tiktok.scraper requires the premium plugin to be installed.") from e
