# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from typing import Any, List
from fastapi import APIRouter, Depends, Path, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.api.deps import get_db

"""
Endpoints de lotes e seus setores.


- `GET /lots/{lot_id}` detalhes do lote.
- `GET /lots/{lot_id}/sectors` lista setores vinculados.
"""

router = APIRouter()

@router.get("/{lot_id}", summary="Detalhar um lote por UUID")
async def get_lot_by_id(
    lot_id: str = Path(..., description="UUID do lote"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    sql = text("""
        SELECT l.id, l.project_id, l.code, l.name, l.description, l.created_at, l.updated_at,
               p.code AS project_code, p.name AS project_name
        FROM lot l
        JOIN project p ON p.id = l.project_id
        WHERE l.id = CAST(:lot_id AS uuid)
    """)
    result = await db.execute(sql, {"lot_id": lot_id})
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Lot not found")
    return dict(row)


@router.get("/{lot_id}/sectors", summary="Listar setores de um lote")
async def list_sectors_by_lot(
    lot_id: str = Path(..., description="UUID do lote"),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> List[dict[str, Any]]:
    sql = text("""
        SELECT s.id, s.code, s.name, s.created_at, s.updated_at
        FROM sector s
        WHERE s.lot_id = CAST(:lot_id AS uuid)
        ORDER BY s.code NULLS LAST, s.name
        LIMIT :limit OFFSET :offset
    """)
    result = await db.execute(sql, {"lot_id": lot_id, "limit": limit, "offset": offset})
    return [dict(r) for r in result.mappings().all()]
