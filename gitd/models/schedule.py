"""ScheduledJob, JobQueue, JobRun models."""

from typing import Optional

from sqlalchemy import Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    phone_serial: Mapped[Optional[str]] = mapped_column(Text)
    priority: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("2"))
    schedule_type: Mapped[str] = mapped_column(Text, nullable=False)
    interval_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    daily_times: Mapped[Optional[str]] = mapped_column(Text)
    config_json: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'{}'"))
    max_duration_s: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("900"))
    is_enabled: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("1"))
    created_at: Mapped[Optional[str]] = mapped_column(Text, server_default=text("(datetime('now'))"))
    updated_at: Mapped[Optional[str]] = mapped_column(Text, server_default=text("(datetime('now'))"))


class JobQueue(Base):
    __tablename__ = "job_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    scheduled_job_id: Mapped[Optional[int]] = mapped_column(Integer)
    phone_serial: Mapped[Optional[str]] = mapped_column(Text)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("2"))
    config_json: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'{}'"))
    max_duration_s: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("900"))
    status: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'pending'"))
    enqueued_at: Mapped[Optional[str]] = mapped_column(Text, server_default=text("(datetime('now'))"))
    started_at: Mapped[Optional[str]] = mapped_column(Text)
    finished_at: Mapped[Optional[str]] = mapped_column(Text)
    pid: Mapped[Optional[int]] = mapped_column(Integer)
    log_file: Mapped[Optional[str]] = mapped_column(Text)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer)
    error_msg: Mapped[Optional[str]] = mapped_column(Text)
    trigger: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'scheduled'"))


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    scheduled_job_id: Mapped[Optional[int]] = mapped_column(Integer)
    phone_serial: Mapped[Optional[str]] = mapped_column(Text)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[Optional[int]] = mapped_column(Integer)
    config_json: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    enqueued_at: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[str]] = mapped_column(Text)
    finished_at: Mapped[Optional[str]] = mapped_column(Text)
    duration_s: Mapped[Optional[int]] = mapped_column(Integer)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer)
    error_msg: Mapped[Optional[str]] = mapped_column(Text)
    log_file: Mapped[Optional[str]] = mapped_column(Text)
    trigger: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'scheduled'"))
    created_at: Mapped[Optional[str]] = mapped_column(Text, server_default=text("(datetime('now'))"))
