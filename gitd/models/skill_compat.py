"""Skill compatibility tracking — per-device execution history."""

from typing import Optional

from sqlalchemy import Float, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SkillRun(Base):
    """One row per skill execution attempt on a device."""

    __tablename__ = "skill_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    device_serial: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    skill_name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)  # 'workflow' or 'action'
    target_name: Mapped[str] = mapped_column(Text, nullable=False)  # e.g. 'send_dm', 'open_app'
    app_version: Mapped[Optional[str]] = mapped_column(Text)  # installed app version at runtime
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'running'"))  # running/ok/fail
    duration_ms: Mapped[Optional[float]] = mapped_column(Float)
    error_msg: Mapped[Optional[str]] = mapped_column(Text)
    params_json: Mapped[Optional[str]] = mapped_column(Text)  # input params snapshot
    started_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("(datetime('now'))"))
    finished_at: Mapped[Optional[str]] = mapped_column(Text)
    is_verify: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )  # 1 = user-triggered verify run


class SkillCompat(Base):
    """Aggregated compatibility status — one row per (device, skill, target).
    Updated after each SkillRun. Used for quick lookups."""

    __tablename__ = "skill_compat"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    device_serial: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    skill_name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_name: Mapped[str] = mapped_column(Text, nullable=False)
    app_version: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # ok / fail / untested
    last_run_at: Mapped[Optional[str]] = mapped_column(Text)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    ok_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
