# FastAPI router for Project endpoints (v1)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_async_db
from .model import Project, ProjectCreate, ProjectUpdate
from . import service
from typing import List

router = APIRouter(prefix="/projects", tags=["projects"])

@router.get("/", response_model=List[Project])
async def read_projects(db: AsyncSession = Depends(get_async_db)):
    return await service.get_projects(db)

@router.get("/{project_id}", response_model=Project)
async def read_project(project_id: int, db: AsyncSession = Depends(get_async_db)):
    project = await service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.post("/", response_model=Project)
async def create_project(project: ProjectCreate, db: AsyncSession = Depends(get_async_db)):
    return await service.create_project(db, project)

@router.put("/{project_id}", response_model=Project)
async def update_project(project_id: int, project: ProjectUpdate, db: AsyncSession = Depends(get_async_db)):
    updated = await service.update_project(db, project_id, project)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated

@router.delete("/{project_id}")
async def delete_project(project_id: int, db: AsyncSession = Depends(get_async_db)):
    await service.delete_project(db, project_id)
    return {"ok": True}
