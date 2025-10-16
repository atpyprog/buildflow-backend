# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.router import router_v1
from fastapi.staticfiles import StaticFiles
from pathlib import Path

"""
BuildFlow – FastAPI entrypoint.

- Cria a instância principal do FastAPI (title/version) e monta /api/v1.
- Garante a existência do diretório de uploads e o serve em /uploads (StaticFiles).
- Configura CORS conforme settings (origens, headers, métodos).
- Expõe /health para diagnóstico rápido do ambiente.
"""

try:
    from fastapi.middleware.cors import CORSMiddleware
    CORS_AVAILABLE = True
except Exception:
    CORS_AVAILABLE = False

start_server = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
)

Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
start_server.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

start_server.include_router(router_v1, prefix="/api/v1")

if CORS_AVAILABLE and settings.CORS_ORIGINS:
    start_server.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.CORS_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

@start_server.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "env": settings.APP_ENV}

# Possiveis testes de conexão com Router
# for r in start_server.routes:
#     try:
#         methods = ",".join(sorted(r.methods)) if hasattr(r, "methods") else "-"
#         print(f"[ROUTE] {methods:20} {r.path}")
#     except Exception as e:
#         print(f"[ROUTE] erro ao listar: {e}")