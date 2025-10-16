# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional, Dict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

"""
Gestão de baselines climáticas.


- Seleciona o melhor `weather_run_day` conforme política (D‑1, latest_before, first_snapshot).
- Executa UPSERT em `weather_baseline`.
- Retorna baseline enriquecida para consultas futuras/comparações.
"""

async def _fetch_one(db: AsyncSession, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
    res = await db.execute(text(sql), params)
    row = res.mappings().first()
    return dict(row) if row else None


async def resolve_run_day_candidate(
    db: AsyncSession,
    project_id: str,
    target_date: date,
    policy: str = "D-1",
) -> dict[str, Any] | None:
    """
    Resolve o weather_run_day candidato para target_date conforme a política:
      - D-1: último run_time do dia anterior ao target_date
      - latest_before: último run_time antes de target_date 00:00
      - first_snapshot: primeiro snapshot disponível para a target_date (mais antigo)
    Retorna a linha de weather_run_day + colunas do run (join) ou None.
    """

    if policy.upper() == "D-1":
        day_before = target_date - timedelta(days=1)
        sql = """
            SELECT wrd.*, wr.run_time, wr.source, wr.timezone
            FROM weather_run_day wrd
            JOIN weather_run wr ON wr.id = wrd.run_id
            WHERE wr.project_id = CAST(:pid AS uuid)
              AND wrd.target_date = :td
              AND DATE(wr.run_time AT TIME ZONE 'UTC') = :dminus1
            ORDER BY wr.run_time DESC
            LIMIT 1
        """
        return await _fetch_one(db, sql, {"pid": project_id, "td": target_date, "dminus1": day_before})


    elif policy.lower() == "latest_before":
        sql = """
            SELECT wrd.*, wr.run_time, wr.source, wr.timezone
            FROM weather_run_day wrd
            JOIN weather_run wr ON wr.id = wrd.run_id
            WHERE wr.project_id = CAST(:pid AS uuid)
              AND wrd.target_date = :td
              AND wr.run_time <= (CAST(:td AS timestamp) AT TIME ZONE 'UTC')
            ORDER BY wr.run_time DESC
            LIMIT 1
        """
        return await _fetch_one(db, sql, {"pid": project_id, "td": target_date})

    elif policy.lower() == "first_snapshot":
        sql = """
            SELECT wrd.*, wr.run_time, wr.source, wr.timezone
            FROM weather_run_day wrd
            JOIN weather_run wr ON wr.id = wrd.run_id
            WHERE wr.project_id = CAST(:pid AS uuid)
              AND wr.run_time <= (CAST(:td AS timestamp) AT TIME ZONE 'UTC')
            ORDER BY wr.run_time ASC
            LIMIT 1
        """
        return await _fetch_one(db, sql, {"pid": project_id, "td": target_date})

    else:
        return None


async def upsert_baseline(
    db: AsyncSession,
    project_id: str,
    target_date: date,
    run_day_id: str,
    policy: str,
    pinned_by: Optional[str] = None,
) -> dict[str, Any]:
    """
    Insere/atualiza a baseline (UNIQUE project_id+target_date).
    Retorna a baseline juntando os dados do run_day e run para feedback.
    """
    # UPSERT baseline
    await db.execute(text("""
        INSERT INTO weather_baseline (project_id, target_date, run_day_id, policy, pinned_by, pinned_at)
        VALUES (CAST(:pid AS uuid), :td, CAST(:rdid AS uuid), :policy, :by, now())
        ON CONFLICT (project_id, target_date) DO UPDATE SET
            run_day_id = EXCLUDED.run_day_id,
            policy     = EXCLUDED.policy,
            pinned_by  = EXCLUDED.pinned_by,
            pinned_at  = now()
    """), {"pid": project_id, "td": target_date, "rdid": run_day_id, "policy": policy, "by": pinned_by})

    # Retorno completo
    row = await _fetch_one(db, """
        SELECT
          wb.id, wb.project_id, wb.target_date, wb.policy, wb.pinned_by, wb.pinned_at,
          wrd.id AS run_day_id, wrd.weather_code, wrd.temp_min_c, wrd.temp_max_c,
          wrd.precipitation_mm, wrd.wind_kmh,
          wr.run_time, wr.source, wr.latitude, wr.longitude, wr.timezone
        FROM weather_baseline wb
        JOIN weather_run_day wrd ON wrd.id = wb.run_day_id
        JOIN weather_run wr ON wr.id = wrd.run_id
        WHERE wb.project_id = CAST(:pid AS uuid) AND wb.target_date = :td
        LIMIT 1
    """, {"pid": project_id, "td": target_date})

    await db.commit()
    if not row:
        raise RuntimeError("Falha ao gravar/retornar baseline")
    return row
