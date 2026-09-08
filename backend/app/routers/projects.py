"""Projects and their environments."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Environment, Project, Variable
from ..schemas import (
    EnvironmentCreate,
    EnvironmentRead,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
)
from ..services import record_audit

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _variable_counts(db: Session, environment_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not environment_ids:
        return {}
    rows = db.execute(
        select(Variable.environment_id, func.count(Variable.id))
        .where(Variable.environment_id.in_(environment_ids))
        .group_by(Variable.environment_id)
    ).all()
    return {row[0]: row[1] for row in rows}


def _project_read(db: Session, project: Project) -> ProjectRead:
    counts = _variable_counts(db, [env.id for env in project.environments])
    return ProjectRead(
        id=project.id,
        slug=project.slug,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        updated_at=project.updated_at,
        environments=[
            EnvironmentRead(
                id=env.id,
                project_id=env.project_id,
                slug=env.slug,
                name=env.name,
                aspect=env.aspect,
                rank=env.rank,
                variable_count=counts.get(env.id, 0),
                updated_at=env.updated_at,
            )
            for env in project.environments
        ],
    )


def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No project with that id.")
    return project


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectRead]:
    projects = db.scalars(
        select(Project).options(selectinload(Project.environments)).order_by(Project.name)
    ).all()
    return [_project_read(db, project) for project in projects]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    project = Project(slug=payload.slug, name=payload.name, description=payload.description)
    db.add(project)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"A project already uses the address '{payload.slug}'."
        ) from exc

    # A new project starts with the three environments almost every app has.
    for rank, (slug, name, aspect) in enumerate(
        [
            ("development", "Development", "clear"),
            ("staging", "Staging", "caution"),
            ("production", "Production", "danger"),
        ]
    ):
        db.add(
            Environment(
                project_id=project.id, slug=slug, name=name, aspect=aspect, rank=rank
            )
        )

    record_audit(
        db,
        action="project.created",
        summary=f"Created project {project.name}",
        project_id=project.id,
    )
    db.commit()
    db.refresh(project)
    return _project_read(db, project)


@router.get("/{project_id}", response_model=ProjectRead)
def read_project(project: Project = Depends(get_project), db: Session = Depends(get_db)) -> ProjectRead:
    return _project_read(db, project)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    payload: ProjectUpdate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
) -> ProjectRead:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    record_audit(
        db,
        action="project.updated",
        summary=f"Updated project {project.name}",
        project_id=project.id,
    )
    db.commit()
    db.refresh(project)
    return _project_read(db, project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project: Project = Depends(get_project), db: Session = Depends(get_db)) -> None:
    name = project.name
    db.delete(project)
    record_audit(db, action="project.deleted", summary=f"Deleted project {name}")
    db.commit()


@router.get("/{project_id}/environments", response_model=list[EnvironmentRead])
def list_environments(
    project: Project = Depends(get_project), db: Session = Depends(get_db)
) -> list[EnvironmentRead]:
    return _project_read(db, project).environments


@router.post(
    "/{project_id}/environments",
    response_model=EnvironmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_environment(
    payload: EnvironmentCreate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
) -> EnvironmentRead:
    environment = Environment(
        project_id=project.id,
        slug=payload.slug,
        name=payload.name,
        aspect=payload.aspect,
        rank=payload.rank,
    )
    db.add(environment)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{project.name} already has an environment called '{payload.slug}'.",
        ) from exc
    record_audit(
        db,
        action="environment.created",
        summary=f"Created environment {environment.name}",
        project_id=project.id,
        environment_id=environment.id,
    )
    db.commit()
    db.refresh(environment)
    return EnvironmentRead(
        id=environment.id,
        project_id=environment.project_id,
        slug=environment.slug,
        name=environment.name,
        aspect=environment.aspect,
        rank=environment.rank,
        variable_count=0,
        updated_at=environment.updated_at,
    )
