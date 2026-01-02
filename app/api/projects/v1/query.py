

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.models.project import Project as ProjectModel
from .model import ProjectCreate, ProjectUpdate
from typing import List, Optional

async def get_projects(db: AsyncSession) -> List[ProjectModel]:
    result = await db.execute(select(ProjectModel))
    return result.scalars().all()

async def get_project(db: AsyncSession, project_id: int) -> Optional[ProjectModel]:
    result = await db.execute(select(ProjectModel).where(ProjectModel.id == project_id))
    return result.scalars().first()

async def create_project(db: AsyncSession, project: ProjectCreate) -> ProjectModel:
    db_project = ProjectModel(**project.dict())
    db.add(db_project)
    await db.commit()
    await db.refresh(db_project)
    return db_project

async def update_project(db: AsyncSession, project_id: int, project: ProjectUpdate) -> Optional[ProjectModel]:
    result = await db.execute(select(ProjectModel).where(ProjectModel.id == project_id))
    db_project = result.scalars().first()
    if db_project:
        for key, value in project.dict(exclude_unset=True).items():
            setattr(db_project, key, value)
        await db.commit()
        await db.refresh(db_project)
    return db_project

async def delete_project(db: AsyncSession, project_id: int) -> None:
    result = await db.execute(select(ProjectModel).where(ProjectModel.id == project_id))
    db_project = result.scalars().first()
    if db_project:
        await db.delete(db_project)
        await db.commit()
