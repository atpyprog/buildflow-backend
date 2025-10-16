# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from typing import Tuple
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings

"""
Utilitário para resolver coordenadas (lat/lon/timezone).


- Busca coordenadas do projeto pai do setor; fallback para defaults do `settings`.
- Define exceção `CoordsUnavailable` para falhas.
"""

class CoordsUnavailable(ValueError):
    pass

async def resolve_coords_for_sector(db: AsyncSession, sector_id: str) -> Tuple[float, float, str]:
    """
    Resolve as coordenadas para um setor.
    Regra atual: usar as coordenadas do PROJETO (fallback p/ defaults do settings).
    """
    q = await db.execute(text("""
        SELECT p.latitude AS lat, p.longitude AS lon
        FROM sector s
        JOIN lot l      ON l.id = s.lot_id
        JOIN project p  ON p.id = l.project_id
        WHERE s.id = CAST(:sid AS uuid)
    """), {"sid": sector_id})
    row = q.mappings().first()

    if row and row["lat"] is not None and row["lon"] is not None:
        return float(row["lat"]), float(row["lon"]), settings.OPEN_METEO_TIMEZONE

    if settings and hasattr(settings, "DEFAULT_LAT") and hasattr(settings, "DEFAULT_LON"):
        if settings.DEFAULT_LAT is not None and settings.DEFAULT_LON is not None:
            return float(settings.DEFAULT_LAT), float(settings.DEFAULT_LON), settings.OPEN_METEO_TIMEZONE

    return 41.14961, -8.61099, settings.OPEN_METEO_TIMEZONE
