# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from typing import Any, List, Optional, Dict, Literal
from datetime import date, datetime, timedelta
from uuid import UUID
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.api.deps import get_db
from app.core.config import settings  # opcional (teste debug)
from app.utils.coords import resolve_coords_for_sector
from app.utils.open_meteo_week import fetch_weather_week
from app.services.weather_normalize import normalize_week_payload, WeatherNormalizationError
from time import perf_counter
import logging

"""
Janela semanal de clima por setor.


- `POST /sectors/{id}/weather/plan-week` planeja captura (não chama API).
- `POST /sectors/{id}/weather/fetch` busca/normaliza e grava (7–14 dias).
- `GET /sectors/{id}/weather/week` retorna janela armazenada.
"""

log = logging.getLogger("weather")

# from app.clients.open_meteo import fetch_week_raw, OpenMeteoHttpError  # (opcional p/ endpoint de teste debug)

router_v1 = APIRouter()

# Schemas
class CoordsOverride(BaseModel):
    lat: float
    lon: float

class PlanWeekIn(BaseModel):
    start_date: Optional[date] = None
    days: int = Field(default=7, ge=1, le=14)
    coords_override: Optional[CoordsOverride] = None
    notes: Optional[str] = None
    requested_by: Optional[str] = None

class FetchWeekIn(PlanWeekIn):
    dedupe: bool = True

class SnapshotOut(BaseModel):
    target_date: date
    weather_code: Optional[int] = None
    temp_min_c: Optional[Decimal] = None
    temp_max_c: Optional[Decimal] = None
    precipitation_mm: Optional[Decimal] = None
    wind_kmh: Optional[Decimal] = None
    forecast_horizon_days: int

class BatchOut(BaseModel):
    id: UUID
    sector_id: UUID
    source: str
    status: str
    requested_by: Optional[str] = None
    requested_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: str
    window_start: date
    window_end: date
    days_count: int
    notes: Optional[str] = None
    error_message: Optional[str] = None

class FetchWeekOut(BaseModel):
    batch: BatchOut
    days_written: int
    days: List[SnapshotOut]

class WeekOut(BaseModel):
    sector_id: UUID
    source: str
    timezone: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    window_start: date
    window_end: date
    snapshots: List[SnapshotOut]

def _validate_coords_override(c: CoordsOverride) -> None:
    if not (-90.0 <= float(c.lat) <= 90.0):
        raise HTTPException(status_code=422, detail=f"invalid latitude: {c.lat}")
    if not (-180.0 <= float(c.lon) <= 180.0):
        raise HTTPException(status_code=422, detail=f"invalid longitude: {c.lon}")

# Helpers DB
async def _insert_batch(db: AsyncSession, sector_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    res = await db.execute(text("""
        INSERT INTO weather_batch (
          sector_id, source, status, requested_by,
          latitude, longitude, timezone,
          window_start, window_end, days_count, notes,
          requested_at, started_at, finished_at, error_message
        ) VALUES (
          CAST(:sid AS uuid), :source, :status, :req_by,
          :lat, :lon, :tz,
          :wstart, :wend, :days, :notes,
          now(), :started, :finished, :err
        )
        RETURNING *;
    """), {
        "sid": sector_id,
        "source": meta.get("source", "open-meteo"),
        "status": meta.get("status", "planned"),
        "req_by": meta.get("requested_by"),
        "lat": meta.get("latitude"),
        "lon": meta.get("longitude"),
        "tz": meta.get("timezone", "UTC"),
        "wstart": meta["window_start"],
        "wend": meta["window_end"],
        "days": meta["days_count"],
        "notes": meta.get("notes"),
        "started": meta.get("started_at"),
        "finished": meta.get("finished_at"),
        "err": meta.get("error_message"),
    })
    row = res.mappings().first()
    if not row:
        raise HTTPException(500, "Falha ao criar weather_batch")
    return dict(row)

async def _insert_snapshots(db: AsyncSession, batch_id: str, sector_id: str, requested_at: datetime, days: List[Dict[str, Any]]) -> int:
    count = 0
    for d in days:
        fh = (d["target_date"] - requested_at.date()).days
        await db.execute(text("""
            INSERT INTO weather_snapshot (
              batch_id, sector_id, target_date,
              weather_code, temp_min_c, temp_max_c,
              precipitation_mm, wind_kmh, forecast_horizon_days
            ) VALUES (
              CAST(:bid AS uuid), CAST(:sid AS uuid), :td,
              :code, :tmin, :tmax, :prec, :wind, :fh
            );
        """), {
            "bid": batch_id,
            "sid": sector_id,
            "td": d["target_date"],
            "code": d.get("weather_code"),
            "tmin": d.get("temp_min_c"),
            "tmax": d.get("temp_max_c"),
            "prec": d.get("precipitation_mm"),
            "wind": d.get("wind_kmh"),
            "fh": max(0, int(fh)),
        })
        count += 1
    return count

# Endpoints
@router_v1.post("/sectors/{sector_id}/weather/plan-week", response_model=BatchOut, summary="Planejar captura de 7–14 dias (não chama provedor)")
async def plan_week(
    payload: PlanWeekIn,
    sector_id: str = Path(..., description="UUID do setor"),
    db: AsyncSession = Depends(get_db),
):
    # valida setor
    chk = await db.execute(text("SELECT 1 FROM sector WHERE id = CAST(:sid AS uuid)"), {"sid": sector_id})
    if not chk.scalar():
        raise HTTPException(404, "Sector not found")

    start = payload.start_date or date.today()
    days = payload.days
    window_end = start + timedelta(days=days - 1)

    if payload.coords_override:
        _validate_coords_override(payload.coords_override)
        lat, lon, tz = payload.coords_override.lat, payload.coords_override.lon, "UTC"
    else:
        try:
            lat, lon, tz = await resolve_coords_for_sector(db, sector_id)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    log.info(
        "weather_plan_week",
        extra={
            "sector_id": sector_id,
            "window_start": str(start),
            "window_end": str(window_end),
            "lat": lat, "lon": lon, "tz": tz,
            "requested_by": payload.requested_by,
        },
    )

    batch_row = await _insert_batch(db, sector_id, {
        "source": "open-meteo",
        "status": "planned",
        "requested_by": payload.requested_by,
        "latitude": lat, "longitude": lon, "timezone": tz,
        "window_start": start, "window_end": window_end, "days_count": days,
        "notes": payload.notes,
    })
    await db.commit()
    return batch_row

@router_v1.post("/sectors/{sector_id}/weather/fetch", response_model=FetchWeekOut, summary="Buscar, normalizar e persistir 7–14 dias")
async def fetch_week(
    payload: FetchWeekIn,
    sector_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
):
    chk = await db.execute(text("SELECT 1 FROM sector WHERE id = CAST(:sid AS uuid)"), {"sid": sector_id})
    if not chk.scalar():
        raise HTTPException(404, "Sector not found")

    start = payload.start_date or date.today()
    days = payload.days
    window_end = start + timedelta(days=days - 1)

    if payload.coords_override:
        _validate_coords_override(payload.coords_override)
        lat, lon, tz = payload.coords_override.lat, payload.coords_override.lon, "UTC"
    else:
        try:
            lat, lon, tz = await resolve_coords_for_sector(db, sector_id)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    log.info(
        "weather_fetch_start",
        extra={
            "sector_id": sector_id,
            "window_start": str(start),
            "window_end": str(window_end),
            "lat": lat, "lon": lon, "tz": tz,
            "requested_by": payload.requested_by,
            "dedupe": payload.dedupe,
        },
    )

    # dedupe: reutiliza último batch recente finalizado para a mesma janela/coordenadas
    if payload.dedupe:
        q = await db.execute(text("""
            SELECT * FROM weather_batch
            WHERE sector_id = CAST(:sid AS uuid)
              AND status = 'completed'
              AND window_start = :ws AND window_end = :we
              AND latitude = :lat AND longitude = :lon
              AND requested_at >= (now() - interval '60 minutes')
            ORDER BY requested_at DESC
            LIMIT 1
        """), {"sid": sector_id, "ws": start, "we": window_end, "lat": lat, "lon": lon})
        reuse = q.mappings().first()
        if reuse:
            days_rows = await db.execute(text("""
                SELECT target_date, weather_code, temp_min_c, temp_max_c, precipitation_mm, wind_kmh,
                       forecast_horizon_days
                FROM weather_snapshot WHERE batch_id = :bid
                ORDER BY target_date
            """), {"bid": reuse["id"]})
            return {
                "batch": dict(reuse),
                "days_written": 0,
                "days": [dict(r) for r in days_rows.mappings().all()]
            }

    requested_at = datetime.utcnow()
    t0 = perf_counter()

    batch_row = await _insert_batch(db, sector_id, {
        "source": "open-meteo",
        "status": "running",
        "requested_by": payload.requested_by,
        "latitude": lat, "longitude": lon, "timezone": tz,
        "window_start": start, "window_end": window_end, "days_count": days,
        "notes": payload.notes,
        "started_at": requested_at,
    })

    try:
        days_data = await fetch_weather_week(lat, lon, start, days)
    except RuntimeError as e:
        err_msg = str(e)[:400]
        await db.execute(text("""
            UPDATE weather_batch SET status='failed', finished_at=now(), error_message=:err
            WHERE id = :bid
        """), {"bid": batch_row["id"], "err": err_msg})
        await db.commit()
        log.error(
            "weather_provider_error",
            extra={
                "batch_id": str(batch_row["id"]),
                "sector_id": sector_id,
                "window_start": str(start),
                "window_end": str(window_end),
                "lat": lat, "lon": lon,
                "error": err_msg,
            },
        )
        raise HTTPException(status_code=502, detail=f"Provider failure: {err_msg}")

    written = await _insert_snapshots(db, str(batch_row["id"]), sector_id, requested_at, days_data)
    elapsed_ms = int((perf_counter() - t0) * 1000)

    res_upd = await db.execute(text("""
        UPDATE weather_batch
        SET status='completed', finished_at=now()
        WHERE id = :bid
        RETURNING *;
    """), {"bid": batch_row["id"]})
    batch_final = dict(res_upd.mappings().first())
    await db.commit()

    days_rows = await db.execute(text("""
        SELECT target_date, weather_code, temp_min_c, temp_max_c, precipitation_mm, wind_kmh,
               forecast_horizon_days
        FROM weather_snapshot WHERE batch_id = :bid
        ORDER BY target_date
    """), {"bid": batch_final["id"]})

    log.info(
        "weather_fetch_done",
        extra={
            "batch_id": str(batch_final["id"]),
            "sector_id": sector_id,
            "days_written": written,
            "elapsed_ms": elapsed_ms,
            "window_start": str(start),
            "window_end": str(window_end),
        },
    )

    return {
        "batch": batch_final,
        "days_written": written,
        "days": [dict(r) for r in days_rows.mappings().all()],
    }

@router_v1.get("/sectors/{sector_id}/weather/week", response_model=WeekOut, summary="Consultar semana gravada (janela)")
async def get_week(
    sector_id: str = Path(..., description="UUID do setor"),
    db: AsyncSession = Depends(get_db),
    start_date: Optional[date] = Query(None, description="Data inicial (YYYY-MM-DD)"),
    days: int = Query(7, ge=1, le=14, description="Quantidade de dias (1–14)"),
    prefer: Literal["latest", "partial", "exact"] = Query("latest"),  # ✅ robusto
    include_batch_meta: bool = Query(False, description="(reservado; ignorado nesta versão)"),
) -> Dict[str, Any]:
    start = start_date or date.today()
    window_end = start + timedelta(days=days - 1)

    sql = text("""
        SELECT DISTINCT ON (ws.target_date)
            ws.target_date,
            ws.weather_code,
            ws.temp_min_c,
            ws.temp_max_c,
            ws.precipitation_mm,
            ws.wind_kmh,
            ws.forecast_horizon_days,
            wb.source,
            wb.timezone,
            wb.latitude,
            wb.longitude,
            wb.finished_at,
            wb.requested_at
        FROM weather_snapshot ws
        JOIN weather_batch wb ON wb.id = ws.batch_id
        WHERE ws.sector_id = CAST(:sid AS uuid)
          AND ws.target_date BETWEEN :ws AND :we
        ORDER BY
            ws.target_date,
            wb.finished_at DESC NULLS LAST,
            wb.requested_at DESC
    """)

    res = await db.execute(sql, {"sid": sector_id, "ws": start, "we": window_end})
    rows = [dict(r) for r in res.mappings().all()]

    if not rows:
        raise HTTPException(status_code=404, detail="No snapshots found for the requested window")

    if prefer == "exact":
        expected = {start + timedelta(days=i) for i in range(days)}
        got = {r["target_date"] for r in rows}
        if got != expected:
            raise HTTPException(status_code=404, detail="Window not fully covered")

    snaps = [{
        "target_date": r["target_date"],
        "weather_code": r.get("weather_code"),
        "temp_min_c": r.get("temp_min_c"),
        "temp_max_c": r.get("temp_max_c"),
        "precipitation_mm": r.get("precipitation_mm"),
        "wind_kmh": r.get("wind_kmh"),
        "forecast_horizon_days": r.get("forecast_horizon_days") or 0,
    } for r in rows]

    meta = rows[0]
    return {
        "sector_id": sector_id,
        "source": meta.get("source") or "open-meteo",
        "timezone": meta.get("timezone") or "UTC",
        "latitude": meta.get("latitude"),
        "longitude": meta.get("longitude"),
        "window_start": start,
        "window_end": window_end,
        "snapshots": snaps,
    }

# Endpoint de debug opcional (comentado):
# @router_v1.get("/_debug/open-meteo/raw")
# async def debug_open_meteo_raw(
#     lat: float,
#     lon: float,
#     start_date: date,
#     days: int = 7,
#     tz: str = settings.OPEN_METEO_TIMEZONE,
# ):
#     try:
#         raw = await fetch_week_raw(lat, lon, start_date, days, timezone=tz)
#         return raw
#     except OpenMeteoHttpError as e:
#         raise HTTPException(status_code=502, detail=str(e))
