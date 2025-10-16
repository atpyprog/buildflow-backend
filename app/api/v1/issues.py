# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from typing import Any, List, Optional, Literal
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.issue_weather import resolve_issue_weather
from app.api.deps import get_db

"""
Gestão de issues (ocorrências) de obra.


- `router_sector`: criar/listar issues por setor (`/sectors/{id}/issues`).
- `router_issue`: operar sobre issue específica (`/issues/{id}`: get/patch/... ).
- Integra contexto meteorológico via `resolve_issue_weather()`.
"""

router_sector = APIRouter()
router_issue  = APIRouter()

Severity = Literal["low", "medium", "high", "critical"]
IssueStatus = Literal["open", "in_progress", "resolved", "canceled"]

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open": {"in_progress", "resolved", "canceled"},
    "in_progress": {"resolved", "canceled"},
    "resolved": set(),
    "canceled": set(),
}

# Schemas IssueCreateIn/IssueUpdateIn/IssueStatusIn/IssueOut
class IssueCreateIn(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    issue_date: date = Field(default_factory=date.today)
    severity: Severity = "medium"
    progress_id: Optional[UUID] = None
    created_by: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "title": "Falta de material",
                "description": "Sem cimento CP-II para a laje do piso 1",
                "issue_date": "2025-10-03",
                "severity": "high",
                "progress_id": None,
                "created_by": "engenharia@obra"
            }
        }
    }

class IssueUpdateIn(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = None
    severity: Optional[Severity] = None
    issue_date: Optional[date] = None

class IssueStatusIn(BaseModel):
    status: IssueStatus
    reason: Optional[str] = None
    changed_by: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"status": "in_progress", "reason": "Equipe acionada", "changed_by": "coordenacao"},
                {"status": "resolved", "reason": "Material entregue", "changed_by": "almoxarifado"},
                {"status": "canceled", "reason": "Lançado por engano", "changed_by": "engenharia"}
            ]
        }
    }

class IssueOut(BaseModel):
    id: UUID
    sector_id: UUID
    progress_id: Optional[UUID] = None
    issue_date: date
    title: str
    description: Optional[str] = None
    severity: Severity
    status: IssueStatus
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    weather_source: Optional[str] = Field(None, description="Origem dos dados meteorológicos (ex: open-meteo)")
    weather_code: Optional[int] = Field(None, description="Código do tempo conforme padrão WMO")
    temp_min_c: Optional[Decimal] = Field(None, description="Temperatura mínima (°C)")
    temp_max_c: Optional[Decimal] = Field(None, description="Temperatura máxima (°C)")
    precipitation_mm: Optional[Decimal] = Field(None, description="Precipitação (mm)")
    wind_kmh: Optional[Decimal] = Field(None, description="Velocidade máxima do vento (km/h)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "8a2a493d-72cd-4a15-9f83-86a0a4d39a12",
                "sector_id": "f4d4ed20-82b1-48d8-aa63-0ba2db768c05",
                "issue_date": "2025-10-10",
                "title": "Concretagem adiada por chuva",
                "description": "Equipe aguardou janela de tempo",
                "severity": "high",
                "status": "open",
                "created_by": "engenharia@obra",
                "weather_source": "open-meteo",
                "weather_code": 61,
                "temp_min_c": 16.5,
                "temp_max_c": 21.0,
                "precipitation_mm": 3.5,
                "wind_kmh": 12.0,
                "created_at": "2025-10-10T11:22:45.211Z",
                "updated_at": "2025-10-10T11:22:45.211Z"
            }
        }
    }


# Helpers _fetch_one/_check_transition
async def _fetch_one(db: AsyncSession, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
    res = await db.execute(text(sql), params)
    row = res.mappings().first()
    return dict(row) if row else None

def _check_transition(old: str, new: str) -> None:
    if old == new:
        return
    allowed = ALLOWED_TRANSITIONS.get(old, set())
    if new not in allowed:
        raise HTTPException(status_code=409, detail=f"Transition not allowed: {old} -> {new}")


@router_sector.post("/{sector_id}/issues", response_model=IssueOut, summary="Criar issue no setor")
async def create_issue(
    payload: IssueCreateIn,
    sector_id: str = Path(..., description="UUID do setor"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not await _fetch_one(db, "SELECT 1 FROM sector WHERE id = CAST(:sid AS uuid)", {"sid": sector_id}):
        raise HTTPException(status_code=404, detail="Sector not found")

    if payload.progress_id:
        if not await _fetch_one(db, "SELECT 1 FROM daily_progress WHERE id = :pid", {"pid": str(payload.progress_id)}):
            raise HTTPException(status_code=404, detail="Progress not found")

    insert = await _fetch_one(db, """
        INSERT INTO issue (sector_id, progress_id, issue_date, title, description, severity, status, created_by)
        VALUES (CAST(:sid AS uuid), CAST(:pid AS uuid), :idate, :title, :desc, :sev, 'open', :who)
        RETURNING *;
    """, {
        "sid": sector_id,
        "pid": str(payload.progress_id) if payload.progress_id else None,
        "idate": payload.issue_date,
        "title": payload.title,
        "desc": payload.description,
        "sev": payload.severity,
        "who": payload.created_by,
    })
    if not insert:
        raise HTTPException(status_code=500, detail="Falha ao criar issue")

    await db.execute(text("""
        INSERT INTO change_log (entity_type, entity_id, action, field, new_value, reason, changed_by)
        VALUES ('issue', :iid, 'created', NULL, :new_value, :reason, :who)
    """), {
        "iid": insert["id"],
        "new_value": f"{insert['title']} ({insert['severity']})",
        "reason": insert.get("description"),
        "who": insert.get("created_by") or "system",
    })

    try:
        weather_context = await resolve_issue_weather(db, sector_id, payload.issue_date)
    except Exception:
        weather_context = None

    if weather_context:
        await db.execute(text("""
            UPDATE issue
            SET
              weather_source   = :src,
              weather_code     = :code,
              temp_min_c       = :tmin,
              temp_max_c       = :tmax,
              precipitation_mm = :prec,
              wind_kmh         = :wind,
              updated_at       = now()
            WHERE id = CAST(:iid AS uuid)
        """), {
            "iid": insert["id"],
            "src": weather_context.get("source"),
            "code": weather_context.get("weather_code"),
            "tmin": weather_context.get("temp_min_c"),
            "tmax": weather_context.get("temp_max_c"),
            "prec": weather_context.get("precipitation_mm"),
            "wind": weather_context.get("wind_kmh"),
        })

        insert.update({
            "weather_source": weather_context.get("source"),
            "weather_code": weather_context.get("weather_code"),
            "temp_min_c": weather_context.get("temp_min_c"),
            "temp_max_c": weather_context.get("temp_max_c"),
            "precipitation_mm": weather_context.get("precipitation_mm"),
            "wind_kmh": weather_context.get("wind_kmh"),
        })

    await db.commit()
    return insert


@router_sector.get("/{sector_id}/issues", response_model=List[IssueOut], summary="Listar issues do setor") #com filtros
async def list_issues_by_sector(
    sector_id: str = Path(..., description="UUID do setor"),
    db: AsyncSession = Depends(get_db),
    status: Optional[IssueStatus] = Query(None),
    severity: Optional[Severity] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[dict[str, Any]]:
    if not await _fetch_one(db, "SELECT 1 FROM sector WHERE id = CAST(:sid AS uuid)", {"sid": sector_id}):
        raise HTTPException(status_code=404, detail="Sector not found")

    cond = ["sector_id = CAST(:sid AS uuid)"]
    params: dict[str, Any] = {"sid": sector_id, "limit": limit, "offset": offset}

    if status:
        cond.append("status = :st"); params["st"] = status
    if severity:
        cond.append("severity = :sev"); params["sev"] = severity
    if date_from:
        cond.append("issue_date >= :df"); params["df"] = date_from
    if date_to:
        cond.append("issue_date <= :dt"); params["dt"] = date_to

    sql = f"""
        SELECT * FROM issue
        WHERE {" AND ".join(cond)}
        ORDER BY issue_date DESC, created_at DESC
        LIMIT :limit OFFSET :offset
    """
    result = await db.execute(text(sql), params)
    return [dict(r) for r in result.mappings().all()]


@router_issue.get("/issues/{issue_id}", response_model=IssueOut, summary="Detalhar issue")
async def get_issue(
    issue_id: str = Path(..., description="UUID do issue"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await _fetch_one(db, "SELECT * FROM issue WHERE id = CAST(:iid AS uuid)", {"iid": issue_id})
    if not row:
        raise HTTPException(status_code=404, detail="Issue not found")
    return row


@router_issue.patch("/issues/{issue_id}", response_model=IssueOut, summary="Atualizar campos do issue (parcial)")
async def update_issue(
    payload: IssueUpdateIn,
    issue_id: str = Path(..., description="UUID do issue"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await _fetch_one(db, "SELECT * FROM issue WHERE id = CAST(:iid AS uuid)", {"iid": issue_id})
    if not row:
        raise HTTPException(status_code=404, detail="Issue not found")

    fields = []
    params: dict[str, Any] = {"iid": issue_id}
    for name in ["title", "description", "severity", "issue_date"]:
        val = getattr(payload, name)
        if val is not None:
            fields.append(f"{name} = :{name}")
            params[name] = val
    if not fields:
        return row

    update = await _fetch_one(db, f"""
        UPDATE issue SET {", ".join(fields)}, updated_at = now()
        WHERE id = CAST(:iid AS uuid)
        RETURNING *;
    """, params)
    if not update:
        raise HTTPException(status_code=500, detail="Falha ao atualizar issue")

    for name in ["title", "description", "severity", "issue_date"]:
        old_v = row.get(name); new_v = update.get(name)
        if old_v != new_v:
            await db.execute(text("""
                INSERT INTO change_log (entity_type, entity_id, action, field, old_value, new_value, changed_by)
                VALUES ('issue', :iid, 'updated', :field, :old, :new, :who)
            """), {
                "iid": issue_id, "field": name,
                "old": str(old_v) if old_v is not None else None,
                "new": str(new_v) if new_v is not None else None,
                "who": "system"
            })

    await db.commit()
    return update


@router_issue.patch("/issues/{issue_id}/status", response_model=IssueOut, summary="Alterar status do issue")
async def set_issue_status(
    payload: IssueStatusIn,
    issue_id: str = Path(..., description="UUID do issue"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await _fetch_one(db, "SELECT id, status FROM issue WHERE id = CAST(:iid AS uuid)", {"iid": issue_id})
    if not row:
        raise HTTPException(status_code=404, detail="Issue not found")

    old = row["status"]; new = payload.status
    _check_transition(old, new)

    update = await _fetch_one(db, """
        UPDATE issue SET status = :st, updated_at = now()
        WHERE id = CAST(:iid AS uuid)
        RETURNING *;
    """, {"iid": issue_id, "st": new})
    if not update:
        raise HTTPException(status_code=500, detail="Falha ao alterar status")

    await db.execute(text("""
        INSERT INTO change_log (entity_type, entity_id, action, field, old_value, new_value, reason, changed_by)
        VALUES ('issue', :iid, 'status_changed', 'status', :old, :new, :reason, :who)
    """), {
        "iid": issue_id,
        "old": old,
        "new": new,
        "reason": payload.reason,
        "who": payload.changed_by or "system"
    })

    await db.commit()
    return update
