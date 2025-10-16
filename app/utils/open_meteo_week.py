# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
import asyncio
from datetime import date, timedelta
from typing import List, Dict, Any, Optional, Coroutine
import httpx
from app.core.config import settings

"""
Utilitário para buscar e normalizar janela semanal (1–14 dias) no Open‑Meteo.


- `fetch_weather_week()` valida intervalo, faz retries com backoff.
- Retorna lista normalizada pronta para persistência.
"""

def _validate_coords(lat: float, lon: float) -> None:
    if lat is None or lon is None:
        raise ValueError("coords unavailable")
    if not (-90.0 <= float(lat) <= 90.0):
        raise ValueError(f"invalid latitude: {lat}")
    if not (-180.0 <= float(lon) <= 180.0):
        raise ValueError(f"invalid longitude: {lon}")


def _validate_window(start_date: date, days: int) -> None:
    if days < 1 or days > 14:
        raise ValueError("days must be between 1 and 14")
    if not isinstance(start_date, date):
        raise ValueError("start_date must be a date")


async def fetch_weather_week(
    lat: float,
    lon: float,
    start_date: date,
    days: int,
    *,
    timeout: Optional[int] = None,
    retries: Optional[int] = None,
    backoff_ms: Optional[int] = None,
) -> list[dict[str, Any]] | None:
    """
    Busca previsão diária (D..D+days-1) no Open-Meteo.
    Retorna lista de dicts com: target_date, weather_code, temp_min_c, temp_max_c,
    precipitation_mm, wind_kmh.
    """

    _validate_coords(lat, lon)
    _validate_window(start_date, days)

    timeout = timeout if timeout is not None else settings.OPEN_METEO_TIMEOUT_S
    retries = retries if retries is not None else settings.OPEN_METEO_RETRIES
    backoff_ms = backoff_ms if backoff_ms is not None else settings.OPEN_METEO_RETRY_BACKOFF_MS

    end_date = start_date + timedelta(days=days - 1)

    params = {
        "latitude": float(lat),
        "longitude": float(lon),
        "daily": settings.OPEN_METEO_DAILY_PARAMS,
        "timezone": settings.OPEN_METEO_TIMEZONE,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }

    base_url = "https://api.open-meteo.com/v1/forecast"

    attempt = 0
    while True:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(base_url, params=params)
                resp.raise_for_status()
                data = resp.json()

            daily = data.get("daily")
            if not daily:
                raise ValueError("provider payload missing 'daily'")

            dates = daily.get("time") or daily.get("date")
            wcode = daily.get("weathercode")
            tmax = daily.get("temperature_2m_max")
            tmin = daily.get("temperature_2m_min")
            prec = daily.get("precipitation_sum")
            wind = daily.get("windspeed_10m_max")

            arrays = [dates, wcode, tmax, tmin, prec, wind]
            if any(a is None for a in arrays):
                raise ValueError("provider payload missing some daily arrays")

            n = len(dates)
            if not all(len(a) == n for a in arrays):
                raise ValueError("provider daily arrays with inconsistent lengths")

            out: List[Dict[str, Any]] = []
            for i in range(n):
                out.append({
                    "target_date": date.fromisoformat(dates[i]),
                    "weather_code": wcode[i],
                    "temp_min_c": tmin[i],
                    "temp_max_c": tmax[i],
                    "precipitation_mm": prec[i],
                    "wind_kmh": wind[i],
                })
            return out

        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as e:
            if attempt < retries:
                attempt += 1
                await asyncio.sleep((backoff_ms * attempt) / 1000.0)
                continue
            raise RuntimeError(f"open-meteo request failed: {e}") from e
        except Exception as e:
            raise RuntimeError(f"open-meteo parse/validation failed: {e}") from e
