# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
import asyncio
from datetime import date as Date
from typing import Any, Dict, Optional, Tuple
import httpx
from app.core.config import settings

"""
Client utilitário (diário) com cache leve para Open‑Meteo.


- Seleciona endpoint forecast/archive conforme a data.
- `fetch_weather(lat, lon, target_date)` → retorna métricas normalizadas básicas.
- Configurado por `settings` (timeout, timezone, parâmetros diários).
"""

# cache leve em memória (chave: (lat, lon, date))
_cache: dict[Tuple[float, float, str], dict[str, Any]] = {}
_CACHE_TTL_SECONDS = 15 * 60  # 15min
_cache_expiry: dict[Tuple[float, float, str], float] = {}

def _cache_key(lat: float, lon: float, target_date: Date) -> Tuple[float, float, str]:
    return (round(lat, 5), round(lon, 5), target_date.isoformat())

def _first(d: dict, key: str):
    arr = d.get(key) or []
    return arr[0] if arr else None

async def _http_get(url: str, params: dict[str, Any], timeout_s: int, retries: int = 1) -> Optional[dict]:
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(0.4 * (attempt + 1))
            else:
                return None
    return None

async def fetch_weather(lat: float, lon: float, target_date: Date) -> Dict[str, Any] | None:
    """
    Consulta Open-Meteo e retorna dados diários:
      weather_source, weather_code, temp_max_c, temp_min_c, precipitation_mm, wind_kmh
    Usa cache leve por 15min para mesma (lat,lon,data).
    """
    if not settings.OPEN_METEO_ENABLED:
        return None

    key = _cache_key(lat, lon, target_date)
    import time as _t
    now = _t.time()
    if key in _cache and _cache_expiry.get(key, 0) > now:
        return _cache[key]

    # endpoint por data: passado/hoje => archive, futuro => forecast
    today = Date.today()
    if target_date <= today:
        base_url = "https://archive-api.open-meteo.com/v1/archive"
    else:
        base_url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": settings.OPEN_METEO_DAILY_PARAMS,
        "timezone": settings.OPEN_METEO_TIMEZONE,
        "start_date": target_date.isoformat(),
        "end_date": target_date.isoformat(),
        "windspeed_unit": "kmh",
        "precipitation_unit": "mm",
    }

    data = await _http_get(base_url, params, timeout_s=settings.OPEN_METEO_TIMEOUT_S, retries=1)
    if not data:
        return None

    daily = data.get("daily") or {}
    result = {
        "weather_source": "open-meteo",
        "weather_code":     _first(daily, "weathercode"),
        "temp_max_c":       _first(daily, "temperature_2m_max"),
        "temp_min_c":       _first(daily, "temperature_2m_min"),
        "precipitation_mm": _first(daily, "precipitation_sum"),
        "wind_kmh":         _first(daily, "windspeed_10m_max"),
    }

    _cache[key] = result
    _cache_expiry[key] = now + _CACHE_TTL_SECONDS
    return result
