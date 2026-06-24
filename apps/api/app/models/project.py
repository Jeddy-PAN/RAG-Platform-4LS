from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Root isolation boundary for documents, retrieval, chat, and eval data."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    retrieval_logs: Mapped[list["RetrievalLog"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
