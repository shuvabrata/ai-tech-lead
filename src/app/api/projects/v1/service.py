from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from . import query
from .model import Project, ProjectCreate, ProjectUpdate


async def get_projects(db: AsyncSession) -> List[Project]:
    return await query.get_projects(db)

async def get_project(db: AsyncSession, project_id: int) -> Project:
    return await query.get_project(db, project_id)

async def create_project(db: AsyncSession, project: ProjectCreate) -> Project:
    return await query.create_project(db, project)

async def update_project(db: AsyncSession, project_id: int, project: ProjectUpdate) -> Project:
    return await query.update_project(db, project_id, project)

async def delete_project(db: AsyncSession, project_id: int) -> None:
    return await query.delete_project(db, project_id)
