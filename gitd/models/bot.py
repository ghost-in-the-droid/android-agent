"""CrawlRun, BotRun models."""

from typing import Optional

from sqlalchemy import Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    run_hex: Mapped[Optional[str]] = mapped_column(Text)
    name: Mapped[Optional[str]] = mapped_column(Text)
    labels: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'[]'"))
    query: Mapped[Optional[str]] = mapped_column(Text)
    tab: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'top'"))
    started_at: Mapped[Optional[str]] = mapped_column(Text)
    ended_at: Mapped[Optional[str]] = mapped_column(Text)
    tiles_processed: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("0"))
    influencers_new: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("0"))
    influencers_known: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("0"))


class BotRun(Base):
    __tablename__ = "bot_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    device: Mapped[Optional[str]] = mapped_column(Text)
    config_json: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'{}'"))
    started_at: Mapped[Optional[str]] = mapped_column(Text)
    finished_at: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'done'"))
    exit_code: Mapped[Optional[int]] = mapped_column(Integer)
    dms_sent: Mapped[Optional[int]] = mapped_column(Integer)
    dms_failed: Mapped[Optional[int]] = mapped_column(Integer)
    video_name: Mapped[Optional[str]] = mapped_column(Text)
    post_action: Mapped[Optional[str]] = mapped_column(Text)
    source_account: Mapped[Optional[str]] = mapped_column(Text)
