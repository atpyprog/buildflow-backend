# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
from datetime import date, timedelta, datetime
from uuid import UUID
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field, conint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from textwrap import shorten
from app.api.deps import get_db

"""
Aplicação de regras de risco climático.


- `POST /sectors/{id}/apply-rules` avalia regras sobre janela de dados (dry_run/commit).
- Gera relatórios diários e issues automáticas; integra com snapshots/batches.
- Endpoints de histórico: listar execuções e detalhar run específico.
"""

router = APIRouter()


Prefer = Literal["latest", "partial", "exact"]
Mode = Literal["dry_run", "commit"]

class RuleIn(BaseModel):
    id: str = Field(..., min_length=1, max_length=60)
    name: Optional[str] = None
    description: Optional[str] = None
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    scope: Literal["per_day"] = "per_day"

    metric: Literal["precipitation_mm", "temp_min_c", "temp_max_c", "wind_kmh", "weather_code"]
    op: Literal[">", ">=", "<", "<=", "=="]
    value: float

    when_horizon_max: Optional[int] = Field(None, ge=0)
    suggest: Optional[Dict[str, str]] = None

class ApplyRulesIn(BaseModel):
    start_date: Optional[date] = None
    days: conint(ge=1, le=14) = 7
    prefer: Prefer = "latest"
    data_source: Literal["auto"] = "auto"
    mode: Mode = "dry_run"
    dedupe_minutes: conint(ge=0, le=720) = 60
    requested_by: Optional[str] = None

    dedupe_key_tmpl: Optional[str] = Field(
        default="issue:{sector_id}:{target_date}:{name}",
        description="string.format com campos do match"
    )
    rules: List[RuleIn]

class ValuePoint(BaseModel):
    target_date: date
    weather_code: Optional[int] = None
    temp_min_c: Optional[Decimal] = None
    temp_max_c: Optional[Decimal] = None
    precipitation_mm: Optional[Decimal] = None
    wind_kmh: Optional[Decimal] = None
    forecast_horizon_days: int

class DayMatch(BaseModel):
    rule_id: str
    name: Optional[str] = None
    severity: str
    metric: str
    op: str
    threshold: float
    actual: Optional[float] = None
    reason: str

class DayReport(BaseModel):
    target_date: date
    values: ValuePoint
    matches: List[DayMatch]

class ActionsOut(BaseModel):
    planned: List[Dict[str, Any]]
    committed: List[Dict[str, Any]]
    skipped: List[Dict[str, Any]]

class ApplyRulesOut(BaseModel):
    context: Dict[str, Any]
    stats: Dict[str, Any]
    days: List[DayReport]
    actions: ActionsOut
    warnings: List[str]

class RulesRunItem(BaseModel):
    id: UUID
    sector_id: UUID
    mode: Literal["dry_run", "commit"]
    executed_at: datetime
    window_start: date
    window_end: date
    days_analyzed: int
    rules_checked: int
    issues_created: int
    status: Literal["ok", "error"]

class RulesHistoryOut(BaseModel):
    items: List[RulesRunItem]
    total: int
    limit: int
    offset: int


def _safe_format(tmpl: str, ctx: dict) -> str:
    """format_map que não quebra se faltar alguma chave — preenche com string vazia."""
    class _D(dict):
        def __missing__(self, key):
            return ""
    return tmpl.format_map(_D(ctx))

async def _sector_exists(db: AsyncSession, sector_id: str) -> bool:
    r = await db.execute(text("SELECT 1 FROM sector WHERE id = CAST(:sid AS uuid)"), {"sid": sector_id})
    return bool(r.scalar())

async def _latest_covering_batch(db: AsyncSession, sector_id: str, ws: date, we: date) -> Optional[Dict[str, Any]]:
    q = await db.execute(text("""
        SELECT *
        FROM weather_batch
        WHERE sector_id = CAST(:sid AS uuid)
          AND status = 'completed'
          AND window_start <= :ws
          AND window_end   >= :we
        ORDER BY finished_at DESC NULLS LAST, requested_at DESC
        LIMIT 1
    """), {"sid": sector_id, "ws": ws, "we": we})
    row = q.mappings().first()
    return dict(row) if row else None

async def _latest_intersecting_batch(db: AsyncSession, sector_id: str, ws: date, we: date) -> Optional[Dict[str, Any]]:
    q = await db.execute(text("""
        SELECT *
        FROM weather_batch
        WHERE sector_id = CAST(:sid AS uuid)
          AND status = 'completed'
          AND window_end >= :ws
          AND window_start <= :we
        ORDER BY finished_at DESC NULLS LAST, requested_at DESC
        LIMIT 1
    """), {"sid": sector_id, "ws": ws, "we": we})
    row = q.mappings().first()
    return dict(row) if row else None

async def _load_snapshots(db: AsyncSession, batch_id: UUID, ws: date, we: date) -> List[Dict[str, Any]]:
    r = await db.execute(text("""
        SELECT target_date, weather_code, temp_min_c, temp_max_c, precipitation_mm, wind_kmh, forecast_horizon_days
        FROM weather_snapshot
        WHERE batch_id = :bid AND target_date BETWEEN :ws AND :we
        ORDER BY target_date
    """), {"bid": batch_id, "ws": ws, "we": we})
    return [dict(m) for m in r.mappings().all()]

def _cmp(op: str, actual: Optional[float], threshold: float) -> bool:
    if actual is None:
        return False
    if op == ">":  return actual >  threshold
    if op == ">=": return actual >= threshold
    if op == "<":  return actual <  threshold
    if op == "<=": return actual <= threshold
    if op == "==": return actual == threshold
    return False

def _extract_metric_value(metric: str, row: Dict[str, Any]) -> Optional[float]:
    v = row.get(metric)
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None

async def _recent_similar_issue_exists(
    db: AsyncSession,
    sector_id: str,
    issue_date: date,
    title: str,
    dedupe_minutes: int,
) -> bool:
    q = await db.execute(text("""
        SELECT 1
        FROM issue
        WHERE sector_id = CAST(:sid AS uuid)
          AND issue_date = :d
          AND title = :t
          AND created_at >= (now() - (:mins || ' minutes')::interval)
        LIMIT 1
    """), {"sid": sector_id, "d": issue_date, "t": title, "mins": str(dedupe_minutes)})
    return bool(q.scalar())

async def _insert_issue_with_weather(
    db: AsyncSession,
    *,
    sector_id: str,
    issue_date: date,
    title: str,
    description: Optional[str],
    severity: str,
    created_by: Optional[str],
    weather_source: Optional[str],
    weather_code: Optional[int],
    temp_min_c: Optional[Decimal],
    temp_max_c: Optional[Decimal],
    precipitation_mm: Optional[Decimal],
    wind_kmh: Optional[Decimal],
) -> dict[str, Any]:
    insert = await db.execute(text("""
        INSERT INTO issue (
          sector_id, progress_id, issue_date, title, description, severity, status, created_by,
          weather_source, weather_code, temp_min_c, temp_max_c, precipitation_mm, wind_kmh
        ) VALUES (
          CAST(:sid AS uuid), NULL, :idate, :title, :desc, :sev, 'open', :who,
          :wsrc, :wcode, :tmin, :tmax, :prec, :wind
        )
        RETURNING *;
    """), {
        "sid": sector_id,
        "idate": issue_date,
        "title": shorten(title or "", 200),
        "desc": description,
        "sev": severity,
        "who": created_by,
        "wsrc": weather_source,
        "wcode": weather_code,
        "tmin": temp_min_c,
        "tmax": temp_max_c,
        "prec": precipitation_mm,
        "wind": wind_kmh,
    })
    row = insert.mappings().first()
    if not row:
        raise HTTPException(500, "Falha ao criar issue")
    new_issue = dict(row)

    await db.execute(text("""
        INSERT INTO change_log (entity_type, entity_id, action, field, new_value, reason, changed_by)
        VALUES ('issue', :iid, 'created', NULL, :summary, :reason, :who)
    """), {
        "iid": new_issue["id"],
        "summary": f"{new_issue['title']} ({new_issue['severity']})",
        "reason": description,
        "who": created_by or "rules-engine",
    })
    return new_issue

@router.post("/sectors/{sector_id}/apply-rules", response_model=ApplyRulesOut, summary="Avaliar regras contra a semana de clima (dry_run por padrão)")
async def apply_rules_endpoint(
    payload: ApplyRulesIn,
    sector_id: str = Path(..., description="UUID do setor"),
    db: AsyncSession = Depends(get_db),
):
    """
    - Busca o último 'weather_batch' completed que cubra (ou intersecte) a janela.
    - Carrega 'weather_snapshot' do intervalo.
    - Avalia as regras 'per_day'.
    - Em 'dry_run', não cria nada; devolve relatório e 'actions.planned'.
    """
    try:
        if not await _sector_exists(db, sector_id):
            raise HTTPException(status_code=404, detail="Sector not found")

        start = payload.start_date or date.today()
        days = payload.days
        window_start = start
        window_end = start + timedelta(days=days - 1)

        batch = await _latest_covering_batch(db, sector_id, window_start, window_end)
        if not batch:
            if payload.prefer == "partial":
                batch = await _latest_intersecting_batch(db, sector_id, window_start, window_end)
                if not batch:
                    raise HTTPException(status_code=404, detail="No snapshots found for requested window (partial)")
            else:
                raise HTTPException(status_code=404, detail="No completed batch covering the requested window")

        snaps = await _load_snapshots(db, batch["id"], window_start, window_end)
        if payload.prefer == "exact":
            expected = {window_start + timedelta(days=i) for i in range(days)}
            got = {row["target_date"] for row in snaps}
            if got != expected:
                raise HTTPException(status_code=404, detail="Window not fully covered (exact)")

        snap_by_day: Dict[date, Dict[str, Any]] = {row["target_date"]: row for row in snaps}
        day_reports: List[DayReport] = []
        total_matches = 0
        planned_actions: List[Dict[str, Any]] = []

        for i in range(days):
            days = window_start + timedelta(days=i)
            row = snap_by_day.get(days, None)

            values = ValuePoint(
                target_date=days,
                weather_code=row.get("weather_code") if row else None,
                temp_min_c=row.get("temp_min_c") if row else None,
                temp_max_c=row.get("temp_max_c") if row else None,
                precipitation_mm=row.get("precipitation_mm") if row else None,
                wind_kmh=row.get("wind_kmh") if row else None,
                forecast_horizon_days=int(row["forecast_horizon_days"]) if row and row.get("forecast_horizon_days") is not None else 0,
            )

            matches: List[DayMatch] = []
            for rule in payload.rules:
                if rule.when_horizon_max is not None:
                    if values.forecast_horizon_days > rule.when_horizon_max:
                        continue

                actual = _extract_metric_value(rule.metric, row or {})
                ok = _cmp(rule.op, actual, float(rule.value))
                if not ok:
                    continue

                reason = f"{rule.metric} {rule.op} {rule.value} (actual={actual})"
                matches.append(DayMatch(
                    rule_id=rule.id,
                    name=rule.name or rule.id,
                    severity=rule.severity,
                    metric=rule.metric,
                    op=rule.op,
                    threshold=float(rule.value),
                    actual=actual,
                    reason=reason,
                ))

                description_context = {
                    "target_date": days.isoformat(),
                    "metric": rule.metric,
                    "op": rule.op,
                    "threshold": rule.value,
                    "actual": actual,
                    "weather_code": (row or {}).get("weather_code"),
                    "temp_min_c": (row or {}).get("temp_min_c"),
                    "temp_max_c": (row or {}).get("temp_max_c"),
                    "precipitation_mm": (row or {}).get("precipitation_mm"),
                    "wind_kmh": (row or {}).get("wind_kmh"),
                }

                title_tmpl = (rule.suggest or {}).get("title")
                desc_tmpl = (rule.suggest or {}).get("description_tmpl")
                title = title_tmpl.format_map(description_context) if title_tmpl else f"{rule.name or rule.id} em {days.isoformat()}"

                try:
                    description = desc_tmpl.format_map(description_context) if desc_tmpl else reason
                except KeyError:
                    description = reason

                planned = {
                    "type": "issue.create",
                    "sector_id": sector_id,
                    "target_date": days.isoformat(),
                    "rule_id": rule.id,
                    "severity": rule.severity,
                    "title": title,
                    "description": description,
                    "dedupe_key": (payload.dedupe_key_tmpl or "issue:{sector_id}:{target_date}:{name}").format(
                        sector_id=sector_id, target_date=days.isoformat(), name=(rule.name or rule.id)
                    ),
                }
                planned_actions.append(planned)

            total_matches += len(matches)
            day_reports.append(DayReport(target_date=days, values=values, matches=matches))

        committed: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []

        if payload.mode == "commit":
            created_count = 0
            for act in planned_actions:
                target_d = date.fromisoformat(act["target_date"])
                title = act["title"]
                rule_id = act["rule_id"]
                if await _recent_similar_issue_exists(
                        db, sector_id, target_d, title, payload.dedupe_minutes
                ):
                    skipped.append({
                        "type": "issue.create",
                        "reason": "deduped_recent",
                        "sector_id": sector_id,
                        "target_date": act["target_date"],
                        "title": title,
                        "rule_id": rule_id,
                    })
                    continue

                snap_row = snap_by_day.get(target_d, {})

                new_issue = await _insert_issue_with_weather(
                    db,
                    sector_id=sector_id,
                    issue_date=target_d,
                    title=title,
                    description=act["description"],
                    severity=act["severity"],
                    created_by=payload.requested_by or "rules-engine",
                    weather_source=batch.get("source"),
                    weather_code=snap_row.get("weather_code"),
                    temp_min_c=snap_row.get("temp_min_c"),
                    temp_max_c=snap_row.get("temp_max_c"),
                    precipitation_mm=snap_row.get("precipitation_mm"),
                    wind_kmh=snap_row.get("wind_kmh"),
                )

                created_count += 1
                committed.append({
                    "type": "issue.create",
                    "sector_id": sector_id,
                    "issue_id": str(new_issue["id"]),
                    "target_date": act["target_date"],
                    "rule_id": rule_id,
                    "title": title,
                })

            await db.execute(text("""
                INSERT INTO rules_run (
                  sector_id, mode, executed_at, window_start, window_end,
                  days_analyzed, rules_checked, issues_created, status
                ) VALUES (
                  CAST(:sid AS uuid), 'commit', now(), :ws, :we,
                  :days, :rcount, :icount, 'ok'
                )
            """), {
                "sid": sector_id, "ws": window_start, "we": window_end,
                "days": days, "rcount": len(payload.rules),
                "icount": created_count,
            })
            await db.commit()

        else:
            await db.execute(text("""
                INSERT INTO rules_run (
                  sector_id, mode, executed_at, window_start, window_end,
                  days_analyzed, rules_checked, issues_created, status
                ) VALUES (
                  CAST(:sid AS uuid), 'dry_run', now(), :ws, :we,
                  :days, :rcount, 0, 'ok'
                )
            """), {
                "sid": sector_id, "ws": window_start, "we": window_end,
                "days": days, "rcount": len(payload.rules),
            })
            await db.commit()

        out = ApplyRulesOut(
            context={
                "sector_id": sector_id,
                "window_start": window_start,
                "window_end": window_end,
                "prefer": payload.prefer,
                "mode": payload.mode,
                "batch_id": str(batch["id"]),
                "source": batch.get("source"),
                "timezone": batch.get("timezone"),
                "latitude": batch.get("latitude"),
                "longitude": batch.get("longitude"),
            },
            stats={"days": days, "matches": total_matches},
            days=day_reports,
            actions=ActionsOut(
                planned=planned_actions,
                committed=committed,
                skipped=skipped
            ),
            warnings=[],
        )
        return out
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(
            status_code=500,
            detail=f"apply-rules failed: {e}; trace={traceback.format_exc()}"
        )

@router.get(
    "/sectors/{sector_id}/rules/history",
    response_model=RulesHistoryOut,
    summary="Listar execuções de apply-rules (histórico)"
)
async def list_rules_history(
    sector_id: str = Path(..., description="UUID do setor"),
    db: AsyncSession = Depends(get_db),
    mode: Optional[Literal["dry_run", "commit"]] = None,
    status: Optional[Literal["ok", "error"]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 50,
    offset: int = 0,
):
    if not await _sector_exists(db, sector_id):
        raise HTTPException(status_code=404, detail="Sector not found")

    cond = ["sector_id = CAST(:sid AS uuid)"]
    params: Dict[str, Any] = {"sid": sector_id, "limit": limit, "offset": offset}

    if mode:
        cond.append("mode = :mode"); params["mode"] = mode
    if status:
        cond.append("status = :st"); params["st"] = status
    if date_from:
        cond.append("executed_at >= :df"); params["df"] = datetime.combine(date_from, datetime.min.time())
    if date_to:
        cond.append("executed_at < :dt"); params["dt"] = datetime.combine(date_to + timedelta(days=1), datetime.min.time())

    where_sql = " AND ".join(cond)

    rules_total = await db.execute(
        text(f"SELECT COUNT(*) FROM rules_run WHERE {where_sql}"),
        params
    )
    total = int(rules_total.scalar() or 0)

    rules_items = await db.execute(text(f"""
        SELECT id, sector_id, mode, executed_at, window_start, window_end,
               days_analyzed, rules_checked, issues_created, status
        FROM rules_run
        WHERE {where_sql}
        ORDER BY executed_at DESC
        LIMIT :limit OFFSET :offset
    """), params)

    items = [dict(m) for m in rules_items.mappings().all()]

    return RulesHistoryOut(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/rules/history/{run_id}",
    response_model=RulesRunItem,
    summary="Detalhar uma execução de apply-rules"
)
async def get_rules_run(
    run_id: str = Path(..., description="UUID do registro em rules_run"),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(text("""
        SELECT id, sector_id, mode, executed_at, window_start, window_end,
               days_analyzed, rules_checked, issues_created, status
        FROM rules_run
        WHERE id = CAST(:rid AS uuid)
        LIMIT 1
    """), {"rid": run_id})
    row = r.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="rules_run not found")
    return dict(row)