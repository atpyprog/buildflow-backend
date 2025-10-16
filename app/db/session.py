# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

"""
Sessão assíncrona do PostgreSQL via SQLAlchemy 2.0.


- Cria `engine` async com pool (pool_size, max_overflow, timeout).
- Garante URL `postgresql+asyncpg://`.
- Expõe `SessionLocal` (async_sessionmaker) para injeção via deps.
"""

if not settings.DATABASE_URL.startswith("postgresql+asyncpg://"):
    raise RuntimeError("DATABASE_URL deve usar o prefixo 'postgresql+asyncpg://' para driver assíncrono.")

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    echo=False,
    future=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)
