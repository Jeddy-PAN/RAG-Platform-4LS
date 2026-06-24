from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import json_dict_type
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class AppSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Non-secret runtime preference stored outside environment variables."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    value: Mapped[dict] = mapped_column(json_dict_type(), default=dict, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
