"""Local tracing — Trace and TraceSpan models.

Mirrors Langfuse's data shape so the same write helpers can fan out to both:
- Always: local SQLite (this module)
- Optionally: Langfuse remote, when LANGFUSE_PUBLIC_KEY is set

A *trace* is one user-message → final-answer round-trip ("turn"). A *span* is
one tool call or LLM generation inside that trace.
"""

from typing import Optional

from sqlalchemy import Float, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Trace(Base):
    __tablename__ = "traces"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # uuid4 hex (32-char)
    # Soft reference (no FK): the trace is opened before the conversation row
    # exists in chat_conversations (save_session_to_db runs in the SSE finally
    # block, after the trace closes). Cascading deletes are handled in
    # delete_conversation_endpoint.
    conversation_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)  # claude-code, on-device, ollama, anthropic
    model: Mapped[str] = mapped_column(Text, server_default=text("''"))
    device: Mapped[str] = mapped_column(Text, server_default=text("''"))
    source: Mapped[str] = mapped_column(Text, server_default=text("'mac'"))  # mac, android
    user_input: Mapped[str] = mapped_column(Text, server_default=text("''"))
    final_output: Mapped[str] = mapped_column(Text, server_default=text("''"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'running'"))  # running, success, error, stopped
    error_text: Mapped[Optional[str]] = mapped_column(Text, server_default=text("''"))
    input_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    cost_usd: Mapped[float] = mapped_column(Float, server_default=text("0"))
    duration_ms: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    started_at: Mapped[str] = mapped_column(Text, nullable=False)  # ISO-8601 UTC
    ended_at: Mapped[Optional[str]] = mapped_column(Text, server_default=text("''"))


# Index for "list traces newest-first" — the dominant query.
Index("ix_traces_started_at", Trace.started_at.desc())
Index("ix_traces_conversation", Trace.conversation_id)


class TraceSpan(Base):
    __tablename__ = "trace_spans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(Text, ForeignKey("traces.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # tool, generation, event
    name: Mapped[str] = mapped_column(Text, nullable=False)  # e.g. "tool:web_search", "llm-call"
    input_json: Mapped[Optional[str]] = mapped_column(Text, server_default=text("''"))
    output_json: Mapped[Optional[str]] = mapped_column(Text, server_default=text("''"))
    level: Mapped[str] = mapped_column(Text, server_default=text("'DEFAULT'"))  # DEFAULT, ERROR
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    ended_at: Mapped[Optional[str]] = mapped_column(Text, server_default=text("''"))
    duration_ms: Mapped[int] = mapped_column(Integer, server_default=text("0"))


Index("ix_trace_spans_trace_id", TraceSpan.trace_id)
