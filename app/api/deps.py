# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from typing import AsyncGenerator
from app.db.session import SessionLocal

"""
Dependências reutilizáveis da API.


- `get_db()` injeta `AsyncSession` (abre/fecha sessão corretamente).
- Padrão usado por endpoints FastAPI para acesso ao Postgres.
"""

async def get_db() -> AsyncGenerator:
    async with SessionLocal() as session:
        yield session
