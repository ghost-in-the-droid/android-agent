"""
Pydantic-settings configuration — reads from .env / environment variables.
Compatible with both pydantic v1 and v2.
"""

from pathlib import Path

try:
    from pydantic_settings import BaseSettings
except ImportError:
    # pydantic v1 fallback — BaseSettings was in pydantic directly
    from pydantic import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from .env and environment variables."""

    # ── Paths ────────────────────────────────────────────────────────────────
    base_dir: Path = Path(__file__).resolve().parent.parent
    db_path: Path = Path(__file__).resolve().parent.parent / "data" / "gitd.db"

    # ── Server ───────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 5055

    # ── Devices ──────────────────────────────────────────────────────────────
    default_device: str = ""  # ADB serial of primary phone (auto-detected if empty)

    # ── API keys (optional, loaded from env) ─────────────────────────────────
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""

    # ── Ollama ──────────────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
