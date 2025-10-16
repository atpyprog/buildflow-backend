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
Resumo de progresso consolidado por lote.


- `GET /{lot_id}/progress/summary` consolida progresso dentro do lote.
- Inclui cabeçalho com informações do projeto associado.
"""

router = APIRouter()

class LotItemOut(BaseModel):
    sector_id: UUID
    sector_code: Optional[str] = None
    total_percent: Decimal
    last_date: Optional[date] = None
    total_photos: int

class LotSummaryOut(BaseModel):
    lot_id: UUID
    project_id: UUID
    project_code: Optional[str] = None
    lot_code: Optional[str] = None
    total_percent: Decimal
    last_update: Optional[date] = None
    items: List[LotItemOut]

@router.get("/{lot_id}/progress/summary", response_model=LotSummaryOut, summary="Resumo de progresso do lote (por setor, com totais)")
async def lot_progress_summary(
    lot_id: str = Path(..., description="UUID do lote"),
    db: AsyncSession = Depends(get_db),
    date_from: Optional[date] = Query(None),
    date_to:   Optional[date] = Query(None),
) -> dict[str, Any]:
    conditions = ["s.lot_id = CAST(:lot_id AS uuid)"]
    params: dict[str, Any] = {"lot_id": lot_id}
    if date_from:
        conditions.append("dp.progress_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        conditions.append("dp.progress_date <= :date_to")
        params["date_to"] = date_to

    sql_items = text(f"""
        SELECT
            s.id   AS sector_id,
            s.code AS sector_code,
            COALESCE(SUM(dp.done_percent), 0) AS total_percent,
            MAX(dp.progress_date)            AS last_date,
            COALESCE(SUM(dp.photos_count), 0) AS total_photos
        FROM sector s
        LEFT JOIN daily_progress dp
          ON dp.sector_id = s.id
         {"AND " + " AND ".join([c for c in conditions[1:]]) if len(conditions) > 1 else ""}
        WHERE {conditions[0]}
        GROUP BY s.id, s.code
        ORDER BY s.code
    """)
    result_items = await db.execute(sql_items, params)
    items = [dict(r) for r in result_items.mappings().all()]

    sql_head = text(f"""
        SELECT
          l.id   AS lot_id,
          l.code AS lot_code,
          p.id   AS project_id,
          p.code AS project_code,
          COALESCE(SUM(dp.done_percent), 0) AS total_percent,
          MAX(dp.progress_date)             AS last_update
        FROM lot l
        JOIN project p ON p.id = l.project_id
        LEFT JOIN sector s ON s.lot_id = l.id
        LEFT JOIN daily_progress dp
          ON dp.sector_id = s.id
         {"AND " + " AND ".join([c for c in conditions[1:]]) if len(conditions) > 1 else ""}
        WHERE l.id = CAST(:lot_id AS uuid)
        GROUP BY l.id, l.code, p.id, p.code
        LIMIT 1
    """)
    result_head = await db.execute(sql_head, params)
    head = result_head.mappings().first()
    if not head:
        return {
            "lot_id": lot_id,
            "project_id": None,
            "project_code": None,
            "lot_code": None,
            "total_percent": 0,
            "last_update": None,
            "items": items,
        }

    return {
        "lot_id": head["lot_id"],
        "project_id": head["project_id"],
        "project_code": head["project_code"],
        "lot_code": head["lot_code"],
        "total_percent": head["total_percent"] or 0,
        "last_update": head["last_update"],
        "items": items,
    }
