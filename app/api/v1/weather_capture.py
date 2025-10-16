# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from datetime import date, timedelta
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, Path, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.services.weather_capture import create_weather_run

"""
Captura e registro de previsões para um projeto.


- `POST /projects/{id}/weather/capture` cria run (weather_run + weather_run_day) para intervalo.
- Valida `date_from/date_to` ou `days` e delega ao serviço `create_weather_run()`.
"""

router = APIRouter()

class CaptureIn(BaseModel):
    date_from: Optional[date] = Field(None, description="Data inicial (incl.)")
    date_to:   Optional[date] = Field(None, description="Data final (incl.)")
    days:      Optional[int]  = Field(None, ge=1, le=14, description="Alternativa: quantidade de dias a partir de hoje")
    run_type:  Optional[str]  = Field("snapshot", description="snapshot|baseline|manual")
    notes:     Optional[str]  = None

class CaptureOut(BaseModel):
    run: dict
    days_written: int
    days: List[dict]
    coords_used: dict

@router.post("/projects/{project_id}/weather/capture", response_model=CaptureOut, summary="Capturar e salvar clima (run + days)")
async def capture_weather(
    payload: CaptureIn,
    project_id: str = Path(..., description="UUID do projeto"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    targets: List[date] = []
    if payload.date_from and payload.date_to:
        if payload.date_from > payload.date_to:
            raise HTTPException(status_code=400, detail="date_from não pode ser maior que date_to")
        cur = payload.date_from
        while cur <= payload.date_to:
            targets.append(cur)
            cur += timedelta(days=1)
    elif payload.days:
        start = date.today()
        for i in range(payload.days):
            targets.append(start + timedelta(days=i))
    else:
        targets = [date.today()]

    result = await create_weather_run(
        db,
        project_id=project_id,
        targets=targets,
        run_type=payload.run_type or "snapshot",
        source="open-meteo",
        notes=payload.notes,
    )
    return result
