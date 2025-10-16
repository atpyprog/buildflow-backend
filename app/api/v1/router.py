# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from fastapi import APIRouter
from app.api.v1 import projects, lots, goals, progress, photos
from app.api.v1 import project_progress, lot_progress
from app.api.v1 import status
from app.api.v1 import issues
from app.api.v1 import weather as weather_api
from app.api.v1 import weather_capture as weather_capture_api
from app.api.v1 import weather_baseline as weather_baseline_api
from app.api.v1 import weather_week
from app.api.v1 import rules

"""
Roteador principal da API v1.


- Agrega e inclui sub-routers (projects, lots, sectors, issues, weather, rules...).
- Centraliza prefixos/tags; importado por `main.py` como `/api/v1`.
"""

router_v1 = APIRouter(tags=["v1"])

# Sub-rotas
router_v1.include_router(projects.router, prefix="/projects", tags=["projects"])
router_v1.include_router(lots.router,     prefix="/lots",     tags=["lots"])

router_v1.include_router(goals.router,    prefix="/sectors",  tags=["goals"])
router_v1.include_router(progress.router, prefix="/sectors",  tags=["progress"])
router_v1.include_router(photos.router,   prefix="/progress", tags=["photos"])

router_v1.include_router(project_progress.router, prefix="/projects", tags=["progress-summary"])
router_v1.include_router(lot_progress.router,     prefix="/lots",     tags=["progress-summary"])
router_v1.include_router(status.router,           prefix="",          tags=["status"])

router_v1.include_router(issues.router_sector, prefix="/sectors", tags=["issues"])
router_v1.include_router(issues.router_issue,  prefix="",         tags=["issues"])

router_v1.include_router(weather_api.router, prefix="", tags=["weather"])
router_v1.include_router(weather_capture_api.router, prefix="", tags=["weather-capture"])
router_v1.include_router(weather_baseline_api.router, prefix="", tags=["weather-baseline"])
router_v1.include_router(weather_week.router_v1, prefix="", tags=["weather-week"])
router_v1.include_router(rules.router, prefix="", tags=["apply-rules"])