# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Iterable, List, Optional, Tuple, Dict, Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.utils.open_meteo import fetch_weather

"""
Serviço de captura/registro de previsões diárias.


- Resolve coordenadas do setor/projeto.
- Chama utils/client Open‑Meteo e grava `weather_run`/`weather_run_day`.
- Retorna resumo com dias gravados e coordenadas usadas.
"""

async def _project_coords(db: AsyncSession, project_id: str) -> Tuple[float, float]:
    """Busca lat/lon do projeto, com fallback para defaults do settings."""
    res = await db.execute(
        text("SELECT latitude AS lat, longitude AS lon FROM project WHERE id = CAST(:pid AS uuid)"),
        {"pid": project_id},
    )
    row = res.mappings().first()
    if row and row["lat"] is not None and row["lon"] is not None:
        return float(row["lat"]), float(row["lon"])
    return settings.DEFAULT_LATITUDE, settings.DEFAULT_LONGITUDE


def _horizon_days(run_time_utc: datetime, target: date) -> int:
    """(target_date - run_time.date) em dias."""
    return (target - run_time_utc.date()).days


async def create_weather_run(
    db: AsyncSession,
    project_id: str,
    targets: Iterable[date],
    *,
    run_type: str = "snapshot",
    source: str = "open-meteo",
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Cria um weather_run para o projeto e grava 1..N linhas em weather_run_day (uma por data).
    Retorna o run + contagem de dias gravados e um resumo.
    """

    lat, lon = await _project_coords(db, project_id)

    res_run = await db.execute(
        text("""
            INSERT INTO weather_run (project_id, run_type, source, latitude, longitude, timezone, notes, raw_payload)
            VALUES (
                CAST(:pid AS uuid), :rtype, :source, :lat, :lon, :tz, :notes, :raw
            )
            RETURNING id, project_id, run_type, run_time, source, latitude, longitude, timezone, notes
        """),
        {
            "pid": project_id,
            "rtype": run_type,
            "source": source,
            "lat": lat,
            "lon": lon,
            "tz": settings.OPEN_METEO_TIMEZONE,
            "notes": notes,
            "raw": None,
        },
    )
    run = res_run.mappings().first()
    if not run:
        raise RuntimeError("Falha ao criar weather_run")

    run_id = run["id"]
    run_time_utc: datetime = run["run_time"]
    if run_time_utc.tzinfo is None:
        run_time_utc = run_time_utc.replace(tzinfo=timezone.utc)

    days_written = 0
    per_day_summary: List[Dict[str, Any]] = []
    for target_date in targets:
        wx = await fetch_weather(lat, lon, target_date)
        if not wx:
            continue

        horizon = _horizon_days(run_time_utc, target_date)

        res_day = await db.execute(
            text("""
                INSERT INTO weather_run_day (
                    run_id, target_date, weather_code, temp_min_c, temp_max_c,
                    precipitation_mm, wind_kmh, forecast_horizon_days
                )
                VALUES (
                    CAST(:rid AS uuid), :d, :code, :tmin, :tmax, :prec, :wind, :hz
                )
                ON CONFLICT (run_id, target_date) DO UPDATE SET
                    weather_code = EXCLUDED.weather_code,
                    temp_min_c = EXCLUDED.temp_min_c,
                    temp_max_c = EXCLUDED.temp_max_c,
                    precipitation_mm = EXCLUDED.precipitation_mm,
                    wind_kmh = EXCLUDED.wind_kmh
                RETURNING id, target_date, weather_code, temp_min_c, temp_max_c, precipitation_mm, wind_kmh, forecast_horizon_days
            """),
            {
                "rid": run_id,
                "d": target_date,
                "code": wx.get("weather_code"),
                "tmin": wx.get("temp_min_c"),
                "tmax": wx.get("temp_max_c"),
                "prec": wx.get("precipitation_mm"),
                "wind": wx.get("wind_kmh"),
                "hz": horizon,
            },
        )
        day_row = res_day.mappings().first()
        if day_row:
            days_written += 1
            per_day_summary.append(dict(day_row))

    await db.commit()

    return {
        "run": dict(run),
        "days_written": days_written,
        "days": per_day_summary,
        "coords_used": {"lat": lat, "lon": lon},
    }
