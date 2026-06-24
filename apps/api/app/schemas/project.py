from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    """Request body for creating a project knowledge base."""

    name: str = Field(min_length=1, max_length=160)
    description: str | None = None


class ProjectUpdate(BaseModel):
    """Request body for editing project metadata."""

    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None


class ProjectRead(BaseModel):
    """Response shape for project metadata."""

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
