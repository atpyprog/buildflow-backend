# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from datetime import date
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, Path, Query, HTTPException
from pydantic import BaseModel, Field, condecimal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from app.api.deps import get_db

"""
Metas diárias por setor (Daily Goals).


- `GET /sectors/{id}/goals` lista metas por intervalo de datas.
- `POST /sectors/{id}/goals` cria/atualiza (UPSERT) meta do dia.
- Registra auditoria em change_log.
"""

router = APIRouter()

# Schemas GoalIn/GoalOut
class CreateGoalIn(BaseModel):
    goal_date: date = Field(..., description="Data da meta (YYYY-MM-DD)")
    target_percent: Optional[condecimal(max_digits=5, decimal_places=2)] = Field(None, ge=0, le=100)
    target_quantity: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    target_unit: Optional[str] = None
    notes: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "goal_date": "2025-10-05",
                "target_percent": 25.50,
                "target_quantity": 100.0,
                "target_unit": "m²",
                "notes": "Meta de concretagem da laje térrea"
            }
        }
    }

class GoalOut(BaseModel):
    id: UUID
    sector_id: UUID
    goal_date: date
    target_percent: Optional[Decimal] = None
    target_quantity: Optional[Decimal] = None
    target_unit: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "3e7f8a9a-8e2d-4f3c-9a12-91a2b5e4f333",
                "sector_id": "f4d4ed20-82b1-48d8-aa63-0ba2db768c05",
                "goal_date": "2025-10-05",
                "target_percent": 25.50,
                "target_quantity": 100.0,
                "target_unit": "m²",
                "notes": "Meta de concretagem da laje térrea",
                "created_at": "2025-10-01T14:20:35.211Z",
                "updated_at": "2025-10-01T14:20:35.211Z"
            }
        }
    }

@router.get("/{sector_id}/goals", response_model=List[GoalOut], summary="Listar metas por setor e intervalo")
async def list_goals(
    sector_id: str = Path(..., description="UUID do setor"),
    db: AsyncSession = Depends(get_db),
    date_from: Optional[date] = Query(None),
    date_to:   Optional[date] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> List[dict[str, Any]]:
    conditions = ["g.sector_id = CAST(:sector_id AS uuid)"]
    params: dict[str, Any] = {"sector_id": sector_id, "limit": limit, "offset": offset}
    if date_from:
        conditions.append("g.goal_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        conditions.append("g.goal_date <= :date_to")
        params["date_to"] = date_to

    sql = text(f"""
        SELECT g.*
        FROM daily_goal g
        WHERE {" AND ".join(conditions)}
        ORDER BY g.goal_date
        LIMIT :limit OFFSET :offset
    """)
    res = await db.execute(sql, params)
    return [dict(row) for row in res.mappings().all()]

@router.post("/{sector_id}/goals", response_model=GoalOut, summary="Criar/atualizar meta do dia (UPSERT)")
async def upsert_goal(
    payload: CreateGoalIn,
    sector_id: str = Path(..., description="UUID do setor"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if payload.target_percent is None and payload.target_quantity is None:
        raise HTTPException(status_code=422, detail="Informe target_percent ou target_quantity.")

    sql = text("""
        INSERT INTO daily_goal (
            sector_id, goal_date, target_percent, target_quantity, target_unit, notes
        ) VALUES (
            CAST(:sector_id AS uuid), :goal_date, :target_percent, :target_quantity, :target_unit, :notes
        )
        ON CONFLICT (sector_id, goal_date) DO UPDATE SET
            target_percent  = EXCLUDED.target_percent,
            target_quantity = EXCLUDED.target_quantity,
            target_unit     = EXCLUDED.target_unit,
            notes           = EXCLUDED.notes,
            updated_at      = now()
        RETURNING *;
    """)
    params = {
        "sector_id": sector_id,
        "goal_date": payload.goal_date,
        "target_percent": payload.target_percent,
        "target_quantity": payload.target_quantity,
        "target_unit": payload.target_unit,
        "notes": payload.notes,
    }
    res = await db.execute(sql, params)
    row = res.mappings().first()
    if not row:
        raise HTTPException(status_code=500, detail="Falha ao salvar meta.")

    await db.execute(text("""
        INSERT INTO change_log (entity_type, entity_id, action, field, new_value, reason, changed_by)
        VALUES ('goal', :gid, 'upsert', NULL, :new_val, :reason, :who)
    """), {
        "gid": row["id"],
        "new_val": f"{row['target_percent'] or row['target_quantity']} {row['target_unit'] or ''}".strip(),
        "reason": row["notes"] or "atualização/criação de meta",
        "who": "system"
    })

    await db.commit()
    return dict(row)
