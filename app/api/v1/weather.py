# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from datetime import date
from typing import Any
from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.core.config import settings
from app.utils.open_meteo import fetch_weather
from app.utils.weather_codes import describe_weather

"""
Consulta de clima (atual/histórico) via Open‑Meteo.


- `GET /weather/test` consulta livre (lat, lon, date).
- `GET /projects/{id}/weather` usa coordenadas do projeto.
- `GET /sectors/{id}/weather` usa coordenadas herdadas do projeto.
- Traduz `weather_code` para descrição humana.
"""

router = APIRouter()

async def _coords_by_project(db: AsyncSession, project_id: str) -> tuple[float, float]:
    row = await db.execute(text("""
        SELECT latitude AS lat, longitude AS lon
        FROM project WHERE id = CAST(:pid AS uuid)
    """), {"pid": project_id})
    r = row.mappings().first()
    if r and r["lat"] is not None and r["lon"] is not None:
        return float(r["lat"]), float(r["lon"])
    return settings.DEFAULT_LATITUDE, settings.DEFAULT_LONGITUDE

async def _coords_by_sector(db: AsyncSession, sector_id: str) -> tuple[float, float]:
    row = await db.execute(text("""
        SELECT p.latitude AS lat, p.longitude AS lon
        FROM sector s
        JOIN lot l ON l.id = s.lot_id
        JOIN project p ON p.id = l.project_id
        WHERE s.id = CAST(:sid AS uuid)
    """), {"sid": sector_id})
    r = row.mappings().first()
    if r and r["lat"] is not None and r["lon"] is not None:
        return float(r["lat"]), float(r["lon"])
    return settings.DEFAULT_LATITUDE, settings.DEFAULT_LONGITUDE

@router.get("/weather/test", summary="Ping Open-Meteo (lat/lon diretos)")
# Localização Porto como padrão/default
async def weather_test(
    db: AsyncSession = Depends(get_db),
    lat: float = Query(41.14961),
    lon: float = Query(-8.61099),
    day: date = Query(date.today()),
) -> dict[str, Any]:
    wx = await fetch_weather(lat, lon, day)
    return {"lat": lat, "lon": lon, "date": str(day), "data": wx, "description": describe_weather(wx.get("weather_code") if wx else None)}

@router.get("/projects/{project_id}/weather", summary="Clima por projeto (usa coords do projeto)")
async def weather_by_project(
    project_id: str = Path(...),
    day: date = Query(date.today()),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    lat, lon = await _coords_by_project(db, project_id)
    wx = await fetch_weather(lat, lon, day)
    if not wx:
        return {"project_id": project_id, "date": str(day), "data": None}
    return {"project_id": project_id, "date": str(day), "data": wx, "description": describe_weather(wx.get("weather_code"))}

@router.get("/sectors/{sector_id}/weather", summary="Clima por setor (herda coords do projeto)")
async def weather_by_sector(
    sector_id: str = Path(...),
    day: date = Query(date.today()),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    lat, lon = await _coords_by_sector(db, sector_id)
    wx = await fetch_weather(lat, lon, day)
    if not wx:
        return {"sector_id": sector_id, "date": str(day), "data": None}
    return {"sector_id": sector_id, "date": str(day), "data": wx, "description": describe_weather(wx.get("weather_code"))}
