# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from typing import Any, Dict, Optional
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

"""
Resolução de contexto meteorológico para uma issue.


- Consulta `weather_snapshot` + `weather_batch` pela data/setor.
- Retorna dicionário com métricas (pode ser None se não houver registros).
- Usado na criação de issues para anexar contexto WX.
"""

async def resolve_issue_weather(db: AsyncSession, sector_id: str, issue_date: date) -> Optional[Dict[str, Any]]:
    sql = """
        SELECT DISTINCT ON (ws.target_date)
            ws.target_date,
            ws.weather_code,
            ws.temp_min_c,
            ws.temp_max_c,
            ws.precipitation_mm,
            ws.wind_kmh,
            wb.source
        FROM weather_snapshot ws
        JOIN weather_batch wb ON wb.id = ws.batch_id
        WHERE ws.sector_id = CAST(:sid AS uuid)
          AND ws.target_date = :idate
        ORDER BY
            ws.target_date,
            wb.finished_at DESC NULLS LAST,
            wb.requested_at DESC
        LIMIT 1
    """
    res = await db.execute(text(sql), {"sid": sector_id, "idate": issue_date})
    row = res.mappings().first()
    return dict(row) if row else None
