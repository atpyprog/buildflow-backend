# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Any, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db

"""
Resumo de progresso consolidado por projeto.


- `GET /{project_id}/progress/summary` agrega por lotes/setores.
- Retorna percentuais, última data e total de fotos.
"""

router = APIRouter()

class ProjectItemOut(BaseModel):
    lot_id: UUID
    lot_code: Optional[str] = None
    sector_id: UUID
    sector_code: Optional[str] = None
    total_percent: Decimal
    last_date: Optional[date] = None
    total_photos: int

class ProjectSummaryOut(BaseModel):
    project_id: UUID
    total_percent: Decimal
    last_update: Optional[date] = None
    items: List[ProjectItemOut]

@router.get("/{project_id}/progress/summary", response_model=ProjectSummaryOut, summary="Resumo de progresso do projeto (por setor, com totais)")
async def project_progress_summary(
    project_id: str = Path(..., description="UUID do projeto"),
    db: AsyncSession = Depends(get_db),
    date_from: Optional[date] = Query(None, description="Filtrar a partir desta data (inclusive)"),
    date_to:   Optional[date] = Query(None, description="Filtrar até esta data (inclusive)"),
) -> dict[str, Any]:
    conditions = [
        "l.project_id = CAST(:project_id AS uuid)"
    ]
    params: dict[str, Any] = {"project_id": project_id}
    if date_from:
        conditions.append("dp.progress_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        conditions.append("dp.progress_date <= :date_to")
        params["date_to"] = date_to

    sql_items = text(f"""
        SELECT
            l.id   AS lot_id,
            l.code AS lot_code,
            s.id   AS sector_id,
            s.code AS sector_code,
            COALESCE(SUM(dp.done_percent), 0) AS total_percent,
            MAX(dp.progress_date)            AS last_date,
            COALESCE(SUM(dp.photos_count), 0) AS total_photos
        FROM lot l
        JOIN sector s ON s.lot_id = l.id
        LEFT JOIN daily_progress dp
          ON dp.sector_id = s.id
         {"AND " + " AND ".join([c for c in conditions[1:]]) if len(conditions) > 1 else ""}
        WHERE {conditions[0]}
        GROUP BY l.id, l.code, s.id, s.code
        ORDER BY l.code, s.code
    """)
    res_items = await db.execute(sql_items, params)
    rows = [dict(r) for r in res_items.mappings().all()]

    sql_total = text(f"""
        SELECT
          COALESCE(SUM(dp.done_percent), 0) AS total_percent,
          MAX(dp.progress_date)             AS last_update
        FROM lot l
        JOIN sector s ON s.lot_id = l.id
        LEFT JOIN daily_progress dp
          ON dp.sector_id = s.id
         {"AND " + " AND ".join([c for c in conditions[1:]]) if len(conditions) > 1 else ""}
        WHERE {conditions[0]}
    """)
    res_total = await db.execute(sql_total, params)
    total_row = res_total.mappings().first() or {"total_percent": 0, "last_update": None}

    return {
        "project_id": project_id,
        "total_percent": total_row["total_percent"] or 0,
        "last_update": total_row["last_update"],
        "items": rows,
    }