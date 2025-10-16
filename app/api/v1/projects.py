# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, Query, Path, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.api.deps import get_db

"""
Endpoints de projetos.


- `GET /projects` lista (com filtro `q` e paginação simples).
- `GET /projects/{project_id}` detalhes do projeto.
- `GET /projects/{project_id}/lots` lista lotes do projeto.
"""

router = APIRouter()

@router.get("", summary="Listar projetos (com paginação simples)")
async def list_projects(
    db: AsyncSession = Depends(get_db),
    query: Optional[str] = Query(default=None, description="Filtro por name/code/city (contém, case-insensitive)"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> List[dict[str, Any]]:
    """
    Retorna projetos com colunas principais. Paginação por limit/offset.
    """
    if query:
        sql = text("""
            SELECT id, code, name, city, state, country, status, start_date, expected_end_date, created_at, updated_at
            FROM project
            WHERE (code ILIKE '%' || :q || '%'
               OR  name ILIKE '%' || :q || '%'
               OR  city ILIKE '%' || :q || '%')
            ORDER BY code
            LIMIT :limit OFFSET :offset
        """)
        result = await db.execute(sql, {"q": query, "limit": limit, "offset": offset})
    else:
        sql = text("""
            SELECT id, code, name, city, state, country, status, start_date, expected_end_date, created_at, updated_at
            FROM project
            ORDER BY code
            LIMIT :limit OFFSET :offset
        """)
        result = await db.execute(sql, {"limit": limit, "offset": offset})

    return [dict(r) for r in result.mappings().all()]


@router.get("/{project_id}", summary="Detalhar um projeto por UUID")
async def get_project_by_id(
    project_id: str = Path(..., description="UUID do projeto"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    sql = text("""
        SELECT id, code, name, address, city, state, country, status, start_date, expected_end_date, created_at, updated_at
        FROM project
        WHERE id = CAST(:project_id AS uuid)
    """)
    result = await db.execute(sql, {"project_id": project_id})
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return dict(row)


@router.get("/{project_id}/lots", summary="Listar lotes de um projeto")
async def list_lots_by_project(
    project_id: str = Path(..., description="UUID do projeto"),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> List[dict[str, Any]]:
    sql = text("""
        SELECT l.id, l.code, l.name, l.description, l.created_at, l.updated_at
        FROM lot l
        WHERE l.project_id = CAST(:project_id AS uuid)
        ORDER BY l.code NULLS LAST, l.name
        LIMIT :limit OFFSET :offset
    """)
    result = await db.execute(sql, {"project_id": project_id, "limit": limit, "offset": offset})
    return [dict(r) for r in result.mappings().all()]
