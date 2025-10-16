# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import date, datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi import HTTPException
from app.services.rules_engine import evaluate_rules

"""
Orquestrador de aplicação de regras e geração de issues automáticas.


- Carrega snapshots/baselines meteorológicos do banco.
- Chama `evaluate_rules()` e aplica deduplicação.
- `apply_rules_orchestrator(mode)` executa dry‑run ou persiste issues (commit).
- Retorna contexto, estatísticas e ações realizadas.
"""

# carregar dados (snapshots/baseline/auto)
async def _pick_batch_for_window(db: AsyncSession, sector_id: str, start: date, end: date, prefer: str) -> Optional[Dict[str, Any]]:
    if prefer not in {"latest", "partial", "exact"}:
        prefer = "latest"

    q = await db.execute(text("""
        SELECT *
        FROM weather_batch
        WHERE sector_id = CAST(:sid AS uuid)
          AND status = 'completed'
          AND window_start <= :ws
          AND window_end   >= :we
        ORDER BY finished_at DESC NULLS LAST, requested_at DESC
        LIMIT 1
    """), {"sid": sector_id, "ws": start, "we": end})
    batch = q.mappings().first()

    if batch:
        return dict(batch)

    if prefer == "partial":
        q2 = await db.execute(text("""
            SELECT *
            FROM weather_batch
            WHERE sector_id = CAST(:sid AS uuid)
              AND status = 'completed'
              AND window_end >= :ws
              AND window_start <= :we
            ORDER BY finished_at DESC NULLS LAST, requested_at DESC
            LIMIT 1
        """), {"sid": sector_id, "ws": start, "we": end})
        b2 = q2.mappings().first()
        return dict(b2) if b2 else None

    if prefer == "exact":
        raise HTTPException(status_code=404, detail="No completed batch covering the requested window")

    return None

async def _load_days_from_snapshots(db: AsyncSession, batch_id: str, start: date, end: date) -> List[Dict[str, Any]]:
    rows = await db.execute(text("""
        SELECT target_date, weather_code, temp_min_c, temp_max_c, precipitation_mm, wind_kmh, forecast_horizon_days
        FROM weather_snapshot
        WHERE batch_id = :bid AND target_date BETWEEN :ws AND :we
        ORDER BY target_date
    """), {"bid": batch_id, "ws": start, "we": end})
    return [dict(r) for r in rows.mappings().all()]

async def _load_day_from_baseline(db: AsyncSession, project_id: str, day: date) -> Optional[Dict[str, Any]]:
    q = await db.execute(text("""
        SELECT b.*, rd.run_time, rd.source, rd.latitude, rd.longitude, rd.timezone
        FROM weather_baseline b
        JOIN weather_run_day rd ON rd.id = b.run_day_id
        WHERE b.project_id = CAST(:pid AS uuid) AND b.target_date = :td
        ORDER BY b.pinned_at DESC
        LIMIT 1
    """), {"pid": project_id, "td": day})
    row = q.mappings().first()
    if not row:
        return None
    return {
        "target_date": row["target_date"],
        "weather_code": row.get("weather_code"),
        "temp_min_c": row.get("temp_min_c"),
        "temp_max_c": row.get("temp_max_c"),
        "precipitation_mm": row.get("precipitation_mm"),
        "wind_kmh": row.get("wind_kmh"),
        "forecast_horizon_days": 0,
    }

async def _resolve_project_id(db: AsyncSession, sector_id: str) -> Optional[str]:
    q = await db.execute(text("SELECT project_id FROM lot WHERE id=(SELECT lot_id FROM sector WHERE id=CAST(:sid AS uuid))"),
                         {"sid": sector_id})
    pid = q.scalar()
    return str(pid) if pid else None

async def load_days_for_apply(
    db: AsyncSession,
    sector_id: str,
    start: date,
    days: int,
    prefer: str,
    data_use: str,
) -> Dict[str, Any]:
    end = start + timedelta(days=days-1)

    project_id = await _resolve_project_id(db, sector_id)
    if not project_id and data_use in {"baseline", "auto"}:
        raise HTTPException(422, "Project not found for sector (baseline/auto needs project)")

    used = "snapshots"
    tz = "UTC"; lat = None; lon = None
    out_days: List[Dict[str, Any]] = []

    if data_use == "snapshots":
        batch = await _pick_batch_for_window(db, sector_id, start, end, prefer)
        if not batch:
            raise HTTPException(404, "No snapshots found for requested window")
        tz = batch["timezone"]; lat = batch["latitude"]; lon = batch["longitude"]
        out_days = await _load_days_from_snapshots(db, str(batch["id"]), start, end)
        used = "snapshots"

    elif data_use == "baseline":
        used = "baseline"
        for i in range(days):
            d = start + timedelta(days=i)
            row = await _load_day_from_baseline(db, project_id, d)
            if row:
                out_days.append(row)

    else:
        batch = await _pick_batch_for_window(db, sector_id, start, end, prefer)
        snaps_by_date = {}
        if batch:
            tz = batch["timezone"]; lat = batch["latitude"]; lon = batch["longitude"]
            snap_rows = await _load_days_from_snapshots(db, str(batch["id"]), start, end)
            snaps_by_date = {r["target_date"]: r for r in snap_rows}

        used = "mixed"
        for i in range(days):
            d = start + timedelta(days=i)
            b = await _load_day_from_baseline(db, project_id, d) if project_id else None
            if b:
                out_days.append(b)
            elif d in snaps_by_date:
                out_days.append(snaps_by_date[d])
            else:
                out_days.append({"target_date": d})

    return {
        "source_used": used,
        "timezone": tz, "latitude": lat, "longitude": lon,
        "window_start": start, "window_end": end,
        "days": out_days
    }

# dedupe & commit
async def _dedupe_hit(db: AsyncSession, sector_id: str, issue_date: date, title: str, dedupe_minutes: int) -> bool:
    q = await db.execute(text("""
        SELECT 1 FROM issue
        WHERE sector_id = CAST(:sid AS uuid)
          AND issue_date = :d
          AND title = :t
          AND created_at >= (now() - (:mm || ' minutes')::interval)
        LIMIT 1
    """), {"sid": sector_id, "d": issue_date, "t": title, "mm": dedupe_minutes})
    return bool(q.scalar())

async def _create_issue(db: AsyncSession, sector_id: str, issue_date: date,
                        title: str, description: Optional[str], severity: str, created_by: str) -> Dict[str, Any]:
    ins = await db.execute(text("""
        INSERT INTO issue (sector_id, issue_date, title, description, severity, status, created_by)
        VALUES (CAST(:sid AS uuid), :d, :t, :desc, :sev, 'open', :who)
        RETURNING *;
    """), {"sid": sector_id, "d": issue_date, "t": title, "desc": description, "sev": severity, "who": created_by})
    row = ins.mappings().first()
    return dict(row) if row else {}

async def apply_rules_orchestrator(
    db: AsyncSession,
    sector_id: str,
    start: date,
    days: int,
    prefer: str,
    data_use: str,
    rules: List[Dict[str, Any]],
    mode: str = "dry_run",
    dedupe_minutes: int = 60,
    performed_by: str = "system",
    attach_to_progress: bool = False,
) -> Dict[str, Any]:
    ctx = await load_days_for_apply(db, sector_id, start, days, prefer, data_use)
    days_data = ctx["days"]

    # avisos de dias vazios
    warnings: List[str] = []
    for d in days_data:
        if "weather_code" not in d and "precipitation_mm" not in d:
            warnings.append(f"missing weather for {d.get('target_date')}")

    # avaliar regras
    engine_res = evaluate_rules(sector_id, days_data, rules)
    planned = engine_res["actions"]["planned"]
    committed: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    # dedupe + commit
    if mode == "commit":
        for act in planned:
            if act["type"] != "create_issue":
                continue
            tdate = act["target"]["date"]
            title = act["title"]

            if await _dedupe_hit(db, sector_id, tdate, title, dedupe_minutes):
                skipped.append({"type": "create_issue", "reason": "dedupe_hit", "title": title, "date": tdate})
                continue

            row = await _create_issue(
                db, sector_id, tdate, title, act.get("description"), act.get("severity", "medium"), performed_by
            )
            if row:
                committed.append({"type": "create_issue", "issue_id": str(row["id"]), "date": tdate, "title": title})

        await db.commit()

    # estrutura da saída
    return {
        "context": {
            "sector_id": sector_id,
            "window_start": ctx["window_start"],
            "window_end": ctx["window_end"],
            "source_used": ctx["source_used"],
            "timezone": ctx["timezone"],
            "latitude": ctx["latitude"],
            "longitude": ctx["longitude"],
        },
        "stats": {
            "rules_evaluated": len(rules),
            "days_evaluated": days,
            "matches_found": sum(len(d["matches"]) for d in engine_res["days"]),
            "actions_planned": len(planned),
            "actions_committed": len(committed),
        },
        "days": engine_res["days"],
        "actions": {
            "planned": planned,
            "committed": committed,
            "skipped": skipped,
        },
        "warnings": warnings,
        "errors": []
    }
