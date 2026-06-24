import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import json_dict_type, uuid_type
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Project-scoped chat thread over one knowledge base."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_project_updated", "project_id", "updated_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        uuid_type(),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(240), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Single user, assistant, or system message in a conversation."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_project_conversation", "project_id", "conversation_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        uuid_type(),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        uuid_type(),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict] = mapped_column(
        json_dict_type(), default=dict, nullable=False
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    citations: Mapped[list["MessageCitation"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )


class MessageCitation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Link from an assistant answer back to the supporting retrieved chunk."""

    __tablename__ = "message_citations"
    __table_args__ = (
        Index("ix_message_citations_project_message", "project_id", "message_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        uuid_type(),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        uuid_type(),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        uuid_type(),
        ForeignKey("chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    citation_index: Mapped[int] = mapped_column(Integer, nullable=False)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation_metadata: Mapped[dict] = mapped_column(
        json_dict_type(), default=dict, nullable=False
    )

    message: Mapped[Message] = relationship(back_populates="citations")
