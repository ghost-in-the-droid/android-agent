"""Phone, TikTokAccount models."""

from typing import Optional

from sqlalchemy import Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Phone(Base):
    __tablename__ = "phones"

    serial: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    nickname: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    model: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    first_seen: Mapped[Optional[str]] = mapped_column(Text)
    last_seen: Mapped[Optional[str]] = mapped_column(Text)
    wifi_ip: Mapped[Optional[str]] = mapped_column(Text)
    wifi_port: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("5555"))
    connection_type: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'usb'"))


class TikTokAccount(Base):
    __tablename__ = "tiktok_accounts"

    handle: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(Text)
    phone_serial: Mapped[Optional[str]] = mapped_column(Text)
    niche: Mapped[Optional[str]] = mapped_column(Text)
    is_default: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("0"))
    is_active: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("1"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[str]] = mapped_column(Text, server_default=text("(datetime('now'))"))
