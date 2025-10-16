# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from datetime import date, datetime
from typing import Any, Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, Path, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from decimal import Decimal
from app.api.deps import get_db
from app.services.weather_baseline import resolve_run_day_candidate, upsert_baseline

"""
Gerência de baselines climáticas por projeto.


- `POST /projects/{id}/weather/baseline/auto` fixa baseline automática (D‑1/latest_before/first_snapshot).
- `POST /projects/{id}/weather/baseline/manual` fixa baseline por `run_day_id`.
- `GET /projects/{id}/weather/baseline` lista baselines por intervalo.
"""

router = APIRouter()

# Schemas
class BaselineAutoIn(BaseModel):
    target_date: date = Field(..., description="Data a ser 'pinada' como baseline")
    policy: str = Field("D-1", description="Política: D-1 | latest_before | first_snapshot")
    pinned_by: Optional[str] = Field(None, description="Quem está fixando a baseline")

class BaselineManualIn(BaseModel):
    target_date: date
    run_day_id: str = Field(..., description="UUID de weather_run_day a ser usado")
    pinned_by: Optional[str] = None
    policy: str = Field("manual", description="Rótulo de política (manual por padrão)")

class BaselineOut(BaseModel):
    id: UUID
    project_id: UUID
    target_date: date
    policy: str
    pinned_by: str | None = None
    pinned_at: datetime | None = None

    run_day_id: UUID
    weather_code: int | None = None
    temp_min_c: Decimal | None = None
    temp_max_c: Decimal | None = None
    precipitation_mm: Decimal | None = None
    wind_kmh: Decimal | None = None

    run_time: datetime
    source: str
    latitude: float | None = None
    longitude: float | None = None
    timezone: str

class BaselineListOut(BaseModel):
    project_id: UUID
    target_date: date
    policy: str
    run_day_id: UUID
    run_time: datetime
    source: str
    weather_code: int | None = None
    temp_min_c: Decimal | None = None
    temp_max_c: Decimal | None = None
    precipitation_mm: Decimal | None = None
    wind_kmh: Decimal | None = None

# Endpoints

@router.post("/projects/{project_id}/weather/baseline/auto", response_model=BaselineOut, summary="Fixar baseline automática por política")
async def baseline_auto(
    payload: BaselineAutoIn,
    project_id: str = Path(..., description="UUID do projeto"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cand = await resolve_run_day_candidate(db, project_id, payload.target_date, policy=payload.policy)
    if not cand:
        raise HTTPException(status_code=404, detail="Nenhum snapshot compatível encontrado para a política/target_date")
    row = await upsert_baseline(db, project_id, payload.target_date, str(cand["id"]), payload.policy, payload.pinned_by)
    return row

@router.post("/projects/{project_id}/weather/baseline/manual", response_model=BaselineOut, summary="Fixar baseline manualmente (informando run_day_id)")
async def baseline_manual(
    payload: BaselineManualIn,
    project_id: str = Path(..., description="UUID do projeto"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    # valida se o run_day_id pertence ao mesmo projeto
    chk = await db.execute(text("""
        SELECT 1
        FROM weather_run_day wrd
        JOIN weather_run wr ON wr.id = wrd.run_id
        WHERE wrd.id = CAST(:rdid AS uuid) AND wr.project_id = CAST(:pid AS uuid)
    """), {"rdid": payload.run_day_id, "pid": project_id})
    if not chk.scalar():
        raise HTTPException(status_code=400, detail="run_day_id não pertence a este projeto ou não existe")

    row = await upsert_baseline(db, project_id, payload.target_date, payload.run_day_id, payload.policy or "manual", payload.pinned_by)
    return row

@router.get("/projects/{project_id}/weather/baseline", response_model=List[BaselineListOut], summary="Listar baselines do projeto por período")
async def list_baselines(
    project_id: str = Path(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from não pode ser maior que date_to")
    res = await db.execute(text("""
        SELECT
          wb.project_id, wb.target_date, wb.policy,
          wrd.id AS run_day_id,
          wr.run_time, wr.source,
          wrd.weather_code, wrd.temp_min_c, wrd.temp_max_c, wrd.precipitation_mm, wrd.wind_kmh
        FROM weather_baseline wb
        JOIN weather_run_day wrd ON wrd.id = wb.run_day_id
        JOIN weather_run wr ON wr.id = wrd.run_id
        WHERE wb.project_id = CAST(:pid AS uuid)
          AND wb.target_date BETWEEN :df AND :dt
        ORDER BY wb.target_date
    """), {"pid": project_id, "df": date_from, "dt": date_to})
    return [dict(m) for m in res.mappings().all()]
