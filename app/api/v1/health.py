# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from time import perf_counter
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db

"""
Diagnóstico do banco de dados.


- `GET /db` verifica conectividade e mede latência.
- Retorna usuário, schema, banco atual e contagem de projetos; trata erros com 503.
"""

router = APIRouter(tags=["Health"])

@router.get("/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    """
    Verifica conexão com o banco e retorna alguns metadados úteis.
    """
    try:
        t0 = perf_counter()
        who = (await db.execute(text("SELECT current_user"))).scalar_one()
        search_path = (await db.execute(text("SELECT current_setting('search_path')"))).scalar_one()
        dbname = (await db.execute(text("SELECT current_database()"))).scalar_one()
        schema = (await db.execute(text("SELECT current_schema()"))).scalar_one()
        project_count = (await db.execute(text("SELECT COUNT(*) FROM project"))).scalar_one()
        latency_ms = (perf_counter() - t0) * 1000.0

        return {
            "db": "ok",
            "latency_ms": round(latency_ms, 2),
            "current_user": who,
            "current_database": dbname,
            "current_schema": schema,
            "search_path": search_path,
            "project_count": project_count,
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={"db": "error", "type": e.__class__.__name__, "message": str(e)},
        )
