# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from typing import Any, Literal, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db

"""
Gestão de status hierárquico (projeto, lote, setor).


- Endpoints PATCH para alterar status de setor/lote/projeto.
- Mantém coerência hierárquica e registra em change_log.
"""

router = APIRouter()

AllowedStatus = Literal["planned","in_progress","on_hold","completed","canceled"]

class StatusIn(BaseModel):
    status: AllowedStatus
    reason: Optional[str] = None
    changed_by: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "in_progress",
                    "reason": "início das atividades",
                    "changed_by": "engenharia@obra"
                },
                {
                    "status": "on_hold",
                    "reason": "chuva forte",
                    "changed_by": "coordenacao@obra"
                },
                {
                    "status": "completed",
                    "reason": "escopo concluído e validado",
                    "changed_by": "engenheiro.responsavel"
                }
            ]
        }
    }

class StatusOut(BaseModel):
    id: UUID
    entity: Literal["project","lot","sector"]
    status: AllowedStatus
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "6f2f0d8a-3b42-4c5b-9a6a-5a2c56f2b0f1",
                "entity": "sector",
                "status": "in_progress",
                "updated_at": "2025-10-02T11:45:10.231Z"
            }
        }
    }

# helpers
ALLOWED_MAP: dict[str, set[str]] = {
    "planned": {"in_progress", "on_hold", "canceled"},
    "in_progress": {"on_hold", "completed", "canceled"},
    "on_hold": {"in_progress", "canceled"},
    "completed": set(),   # terminal
    "canceled": set(),    # terminal
}

async def _fetch_one(db: AsyncSession, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
    res = await db.execute(text(sql), params)
    row = res.mappings().first()
    return dict(row) if row else None

def _check_transition(old: str, new: str) -> None:
    if old == new:
        return
    allowed_next = ALLOWED_MAP.get(old, set())
    if new not in allowed_next:
        raise HTTPException(
            status_code=409,
            detail=f"Transition not allowed: {old} -> {new}"
        )

# Sector Status
@router.patch("/v1/sectors/{sector_id}/status", response_model=StatusOut, summary="Alterar status de um setor")
async def set_sector_status(
    payload: StatusIn,
    sector_id: str = Path(..., description="UUID do setor"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    # buscar status atual e lot_id
    row = await _fetch_one(db, """
        SELECT id, status, lot_id FROM sector WHERE id = CAST(:sid AS uuid)
    """, {"sid": sector_id})
    if not row:
        raise HTTPException(status_code=404, detail="Sector not found")

    old = row["status"]
    new = payload.status
    _check_transition(old, new)

    # aplicar mudança
    update = await _fetch_one(db, """
        UPDATE sector SET status = :new, updated_at = now()
        WHERE id = CAST(:sid AS uuid)
        RETURNING id, status, updated_at
    """, {"sid": sector_id, "new": new})
    if not update:
        raise HTTPException(status_code=500, detail="Failed to update sector status")

    # se setor foi para in_progress e o lote estava planned -> "bump" o lote
    if new == "in_progress":
        await db.execute(text("""
            UPDATE lot SET status = 'in_progress', updated_at = now()
            WHERE id = :lot_id AND status = 'planned'
        """), {"lot_id": row["lot_id"]})

    # se setor foi para completed, verificar se todos setores do lote estão completed -> completar lote
    if new == "completed":
        done = await _fetch_one(db, """
            SELECT
              SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed_count,
              COUNT(*) AS total
            FROM sector WHERE lot_id = :lot_id
        """, {"lot_id": row["lot_id"]})
        if done and done["completed_count"] == done["total"] and done["total"] > 0:
            await db.execute(text("""
                UPDATE lot SET status = 'completed', updated_at = now()
                WHERE id = :lot_id
            """), {"lot_id": row["lot_id"]})

            await db.execute(text("""
                UPDATE project SET status = 'completed', updated_at = now()
                WHERE id = (SELECT project_id FROM lot WHERE id = :lot_id)
                  AND NOT EXISTS (
                    SELECT 1 FROM lot
                    WHERE project_id = (SELECT project_id FROM lot WHERE id = :lot_id)
                      AND status <> 'completed'
                  )
            """), {"lot_id": row["lot_id"]})

            await db.execute(text("""
                INSERT INTO change_log (entity_type, entity_id, action, field, old_value, new_value, reason, changed_by)
                VALUES ('sector', CAST(:sid AS uuid), 'status_changed', 'status', :old, :new, :reason, :who)
            """), {
                "sid": sector_id,
                "old": old,
                "new": new,
                "reason": payload.reason,
                "who": payload.changed_by or "system"
            })

    await db.commit()
    return {"id": update["id"], "entity": "sector", "status": update["status"], "updated_at": update["updated_at"]}

# lot status
@router.patch("/v1/lots/{lot_id}/status", response_model=StatusOut, summary="Alterar status de um lote")
async def set_lot_status(
    payload: StatusIn,
    lot_id: str = Path(..., description="UUID do lote"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await _fetch_one(db, "SELECT id, status, project_id FROM lot WHERE id = CAST(:lid AS uuid)", {"lid": lot_id})
    if not row:
        raise HTTPException(status_code=404, detail="Lot not found")

    old = row["status"]; new = payload.status
    _check_transition(old, new)

    # para completar o lote, todos setores precisam estar completed
    if new == "completed":
        chk = await _fetch_one(db, """
            SELECT COUNT(*) AS open_count
            FROM sector WHERE lot_id = :lid AND status <> 'completed'
        """, {"lid": lot_id})
        if chk and chk["open_count"] > 0:
            raise HTTPException(status_code=409, detail="Cannot complete lot: there are sectors not completed")

    upd = await _fetch_one(db, """
        UPDATE lot SET status = :new, updated_at = now()
        WHERE id = CAST(:lid AS uuid)
        RETURNING id, status, updated_at
    """, {"lid": lot_id, "new": new})
    if not upd:
        raise HTTPException(status_code=500, detail="Failed to update lot status")

    # se lote foi para completed, checar se todos lotes do projeto estão completed -> completar projeto
    if new == "completed":
        await db.execute(text("""
            UPDATE project SET status = 'completed', updated_at = now()
            WHERE id = :pid
              AND NOT EXISTS (SELECT 1 FROM lot WHERE project_id = :pid AND status <> 'completed')
        """), {"pid": row["project_id"]})

        await db.execute(text("""
            INSERT INTO change_log (entity_type, entity_id, action, field, old_value, new_value, reason, changed_by)
            VALUES ('lot', CAST(:lid AS uuid), 'status_changed', 'status', :old, :new, :reason, :who)
        """), {
            "lid": lot_id,
            "old": old,
            "new": new,
            "reason": payload.reason,
            "who": payload.changed_by or "system"
        })

    await db.commit()
    return {"id": upd["id"], "entity": "lot", "status": upd["status"], "updated_at": upd["updated_at"]}

# project status
@router.patch("/v1/projects/{project_id}/status", response_model=StatusOut, summary="Alterar status de um projeto")
async def set_project_status(
    payload: StatusIn,
    project_id: str = Path(..., description="UUID do projeto"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await _fetch_one(db, "SELECT id, status FROM project WHERE id = CAST(:pid AS uuid)", {"pid": project_id})
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    old = row["status"]; new = payload.status
    _check_transition(old, new)

    # para completar o projeto, todos lotes precisam estar completed
    if new == "completed":
        chk = await _fetch_one(db, """
            SELECT COUNT(*) AS open_count
            FROM lot WHERE project_id = CAST(:pid AS uuid) AND status <> 'completed'
        """, {"pid": project_id})
        if chk and chk["open_count"] > 0:
            raise HTTPException(status_code=409, detail="Cannot complete project: there are lots not completed")

    upd = await _fetch_one(db, """
        UPDATE project SET status = :new, updated_at = now()
        WHERE id = CAST(:pid AS uuid)
        RETURNING id, status, updated_at
    """, {"pid": project_id, "new": new})
    if not upd:
        raise HTTPException(status_code=500, detail="Failed to update project status")

    await db.execute(text("""
        INSERT INTO change_log (entity_type, entity_id, action, field, old_value, new_value, reason, changed_by)
        VALUES ('project', CAST(:pid AS uuid), 'status_changed', 'status', :old, :new, :reason, :who)
    """), {
        "pid": project_id,
        "old": old,
        "new": new,
        "reason": payload.reason,
        "who": payload.changed_by or "system"
    })

    await db.commit()
    return {"id": upd["id"], "entity": "project", "status": upd["status"], "updated_at": upd["updated_at"]}
