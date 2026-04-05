"""ChatConversation and ChatMessageRow models — persistent agent chat storage."""

from typing import Optional

from sqlalchemy import ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ChatConversation(Base):
    __tablename__ = "chat_conversations"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # 8-char UUID
    device: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, server_default=text("'claude-code'"))
    model: Mapped[str] = mapped_column(Text, server_default=text("'sonnet'"))
    title: Mapped[str] = mapped_column(Text, server_default=text("''"))
    created_at: Mapped[str] = mapped_column(Text, nullable=False)  # ISO-8601
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)  # ISO-8601
    message_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class ChatMessageRow(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    conversation_id: Mapped[str] = mapped_column(
        Text, ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, server_default=text("''"))
    tool_name: Mapped[Optional[str]] = mapped_column(Text, server_default=text("''"))
    tool_args: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'{}'"))  # JSON string
    tool_id: Mapped[Optional[str]] = mapped_column(Text, server_default=text("''"))
    created_at: Mapped[str] = mapped_column(Text, nullable=False)  # ISO-8601
