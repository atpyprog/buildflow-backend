# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from typing import Any, List, Optional
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, Path, Query, HTTPException
from pydantic import BaseModel, Field, condecimal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.core.config import settings
from app.utils.open_meteo import fetch_weather

"""
Progresso diário dos setores.


- `GET /{sector_id}/progress` lista progressos com filtros.
- `GET /{sector_id}/progress/summary` resumo acumulado.
- `POST /{sector_id}/progress` cria/atualiza (UPSERT) e integra Open‑Meteo; audita mudanças.
"""

router = APIRouter()

def _to_str(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, (Decimal,)):
        return str(v)
    return str(v)

_AUDIT_FIELDS = [
    "done_percent", "done_quantity", "done_unit",
    "blockers", "notes", "reported_by",
    "weather_source", "weather_code",
    "temp_min_c", "temp_max_c", "precipitation_mm", "wind_kmh",
]

class CreateProgressIn(BaseModel):
    progress_date: date = Field(..., description="Data do progresso (YYYY-MM-DD)")
    done_percent: Optional[condecimal(max_digits=5, decimal_places=2)] = Field(None, ge=0, le=100)
    done_quantity: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    done_unit: Optional[str] = None
    blockers: Optional[str] = None
    notes: Optional[str] = None
    reported_by: Optional[str] = None
    weather_source: Optional[str] = None
    weather_code: Optional[int] = None
    temp_min_c: Optional[condecimal(max_digits=5, decimal_places=2)] = None
    temp_max_c: Optional[condecimal(max_digits=5, decimal_places=2)] = None
    precipitation_mm: Optional[condecimal(max_digits=6, decimal_places=2)] = None
    wind_kmh: Optional[condecimal(max_digits=6, decimal_places=2)] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "progress_date": "2025-10-02",
                "done_percent": 10.0,
                "done_quantity": 50.0,
                "done_unit": "m²",
                "blockers": "chuva leve atrapalhou",
                "notes": "Alvenaria concluída até metade do setor",
                "reported_by": "engenheiro A"
            }
        }
    }

class ProgressOut(BaseModel):
    id: UUID
    sector_id: UUID
    progress_date: date
    done_percent: Optional[Decimal] = None
    done_quantity: Optional[Decimal] = None
    done_unit: Optional[str] = None
    blockers: Optional[str] = None
    notes: Optional[str] = None
    photos_count: Optional[int] = 0
    reported_by: Optional[str] = None
    reported_at: Optional[datetime] = None
    weather_source: Optional[str] = None
    weather_code: Optional[int] = None
    temp_min_c: Optional[Decimal] = None
    temp_max_c: Optional[Decimal] = None
    precipitation_mm: Optional[Decimal] = None
    wind_kmh: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "8a2a493d-72cd-4a15-9f83-86a0a4d39a12",
                "sector_id": "f4d4ed20-82b1-48d8-aa63-0ba2db768c05",
                "progress_date": "2025-10-02",
                "done_percent": 10.0,
                "done_quantity": 50.0,
                "done_unit": "m²",
                "blockers": "chuva leve atrapalhou",
                "notes": "Alvenaria concluída até metade do setor",
                "photos_count": 2,
                "reported_by": "engenheiro A",
                "reported_at": "2025-10-02T11:22:45.211Z",
                "weather_source": "open-meteo",
                "weather_code": 61,
                "temp_min_c": 16.5,
                "temp_max_c": 21.0,
                "precipitation_mm": 3.5,
                "wind_kmh": 12.0,
                "created_at": "2025-10-02T11:22:45.211Z",
                "updated_at": "2025-10-02T11:22:45.211Z"
            }
        }
    }

async def _get_coords_for_sector_project(db: AsyncSession, sector_id: str) -> tuple[float, float]:
    """
    Busca latitude/longitude do PROJETO ao qual o setor pertence.
    Se o projeto não tiver coords, retorna os defaults do settings.
    """
    sql = text("""
        SELECT p.latitude AS lat, p.longitude AS lon
        FROM sector s
        JOIN lot l      ON l.id = s.lot_id
        JOIN project p  ON p.id = l.project_id
        WHERE s.id = CAST(:sid AS uuid)
        LIMIT 1
    """)
    res = await db.execute(sql, {"sid": sector_id})
    row = res.mappings().first()
    if row and row["lat"] is not None and row["lon"] is not None:
        return float(row["lat"]), float(row["lon"])
    return settings.DEFAULT_LATITUDE, settings.DEFAULT_LONGITUDE

@router.get("/{sector_id}/progress", response_model=List[ProgressOut], summary="Listar progresso por setor e intervalo")
async def list_progress(
    sector_id: str = Path(..., description="UUID do setor"),
    db: AsyncSession = Depends(get_db),
    date_from: Optional[date] = Query(None),
    date_to:   Optional[date] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> List[dict[str, Any]]:
    conditions = ["dp.sector_id = CAST(:sector_id AS uuid)"]
    params: dict[str, Any] = {"sector_id": sector_id, "limit": limit, "offset": offset}
    if date_from:
        conditions.append("dp.progress_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        conditions.append("dp.progress_date <= :date_to")
        params["date_to"] = date_to

    sql = text(f"""
        SELECT dp.*
        FROM daily_progress dp
        WHERE {" AND ".join(conditions)}
        ORDER BY dp.progress_date
        LIMIT :limit OFFSET :offset
    """)
    res = await db.execute(sql, params)
    return [dict(row) for row in res.mappings().all()]

@router.get("/{sector_id}/progress/summary", summary="Resumo acumulado de % por setor")
async def progress_summary(
    sector_id: str = Path(..., description="UUID do setor"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    sql_total = text("""
        SELECT COALESCE(SUM(done_percent), 0) AS total_percent
        FROM daily_progress
        WHERE sector_id = CAST(:sector_id AS uuid)
    """)
    res_total = await db.execute(sql_total, {"sector_id": sector_id})
    total_percent = float(res_total.scalar() or 0)

    sql_last = text("""
        SELECT progress_date
        FROM daily_progress
        WHERE sector_id = CAST(:sector_id AS uuid)
        ORDER BY progress_date DESC
        LIMIT 1
    """)
    res_last = await db.execute(sql_last, {"sector_id": sector_id})
    last_date = res_last.scalar()

    return {
        "sector_id": sector_id,
        "cumulative_percent": total_percent,
        "last_update": str(last_date) if last_date else None,
    }

@router.post("/{sector_id}/progress", response_model=ProgressOut, summary="Criar/atualizar progresso do dia (UPSERT)")
async def upsert_progress(
    payload: CreateProgressIn,
    sector_id: str = Path(..., description="UUID do setor"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if payload.done_percent is None and payload.done_quantity is None:
        raise HTTPException(status_code=422, detail="Informe done_percent ou done_quantity.")

    old_row_result = await db.execute(text("""
        SELECT *
        FROM daily_progress
        WHERE sector_id = CAST(:sector_id AS uuid)
          AND progress_date = :progress_date
        LIMIT 1
    """), {"sector_id": sector_id, "progress_date": payload.progress_date})
    old_row = old_row_result.mappings().first()
    old_row = dict(old_row) if old_row else None

    has_manual_weather = any([
        payload.weather_code is not None,
        payload.temp_min_c is not None,
        payload.temp_max_c is not None,
        payload.precipitation_mm is not None,
        payload.wind_kmh is not None,
    ])
    weather_params: dict[str, Any] = {}

    if not has_manual_weather and settings.OPEN_METEO_ENABLED:
        try:
            lat, lon = await _get_coords_for_sector_project(db, sector_id)
            wx = await fetch_weather(lat, lon, payload.progress_date)
            if wx:
                weather_params.update(wx)  # inclui weather_source="open-meteo" e demais campos
        except Exception:
            pass

    sql = text("""
        INSERT INTO daily_progress (
            sector_id, progress_date, done_percent, done_quantity, done_unit,
            blockers, notes, reported_by,
            weather_source, weather_code, temp_min_c, temp_max_c, precipitation_mm, wind_kmh
        ) VALUES (
            CAST(:sector_id AS uuid), :progress_date, :done_percent, :done_quantity, :done_unit,
            :blockers, :notes, :reported_by,
            :weather_source, :weather_code, :temp_min_c, :temp_max_c, :precipitation_mm, :wind_kmh
        )
        ON CONFLICT (sector_id, progress_date) DO UPDATE SET
            done_percent     = EXCLUDED.done_percent,
            done_quantity    = EXCLUDED.done_quantity,
            done_unit        = EXCLUDED.done_unit,
            blockers         = EXCLUDED.blockers,
            notes            = EXCLUDED.notes,
            reported_by      = EXCLUDED.reported_by,
            weather_source   = EXCLUDED.weather_source,
            weather_code     = EXCLUDED.weather_code,
            temp_min_c       = EXCLUDED.temp_min_c,
            temp_max_c       = EXCLUDED.temp_max_c,
            precipitation_mm = EXCLUDED.precipitation_mm,
            wind_kmh         = EXCLUDED.wind_kmh,
            updated_at       = now()
        RETURNING *;
    """)

    params = payload.model_dump()
    params.update(weather_params)
    params["sector_id"] = sector_id

    result = await db.execute(sql, params)
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=500, detail="Falha ao salvar progresso.")
    new_row = dict(row)

    # change_log
    changed_by = payload.reported_by or "system"
    reason = payload.notes or "atualização/criação de progresso"

    if old_row is None:
        summary = _to_str(new_row.get("done_percent")) or _to_str(new_row.get("done_quantity")) or "0"
        await db.execute(text("""
            INSERT INTO change_log (entity_type, entity_id, action, field, new_value, reason, changed_by)
            VALUES ('progress', :pid, 'created', NULL, :new_value, :reason, :who)
        """), {
            "pid": new_row["id"],
            "new_value": summary,
            "reason": reason,
            "who": changed_by
        })
    else:
        for f in _AUDIT_FIELDS:
            old_v = old_row.get(f)
            new_v = new_row.get(f)
            if old_v != new_v:
                await db.execute(text("""
                    INSERT INTO change_log (entity_type, entity_id, action, field, old_value, new_value, reason, changed_by)
                    VALUES ('progress', :pid, 'updated', :field, :old_value, :new_value, :reason, :who)
                """), {
                    "pid": new_row["id"],
                    "field": f,
                    "old_value": _to_str(old_v),
                    "new_value": _to_str(new_v),
                    "reason": reason,
                    "who": changed_by
                })

    await db.commit()
    return new_row
