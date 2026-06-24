import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate


def create_project(db: Session, payload: ProjectCreate) -> Project:
    """Create a project and translate duplicate names to HTTP 409."""

    project = Project(name=payload.name, description=payload.description)
    db.add(project)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project name already exists",
        ) from exc
    db.refresh(project)
    return project


def list_projects(db: Session) -> list[Project]:
    """List projects ordered for sidebar display."""

    return list(db.scalars(select(Project).order_by(Project.updated_at.desc())))


def get_project(db: Session, project_id: uuid.UUID) -> Project:
    """Fetch one project or raise HTTP 404."""

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project


def update_project(db: Session, project_id: uuid.UUID, payload: ProjectUpdate) -> Project:
    """Update project metadata and preserve unique-name errors."""

    project = get_project(db, project_id)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(project, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project name already exists",
        ) from exc
    db.refresh(project)
    return project


def delete_project(db: Session, project_id: uuid.UUID) -> None:
    """Delete a project and rely on database cascades for owned records."""

    project = get_project(db, project_id)
    db.delete(project)
    db.commit()
