# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from datetime import date
from typing import Any, Dict
import httpx
from app.core.config import settings

"""
Client HTTP (Open‑Meteo – previsão diária/semana).


- Define base URL pública e exceção `OpenMeteoHttpError`.
- `fetch_week_raw(lat, lon, start_date, days, *, timezone, timeout_s)` retorna JSON bruto.
- Responsável por timeouts/retries básicos e resposta fiel da API.
"""

OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"


class OpenMeteoHttpError(RuntimeError):
    """Erro HTTP ao consultar o Open-Meteo."""

async def fetch_week_raw(
    lat: float,
    lon: float,
    start_date: date,
    days: int,
    *,
    timezone: str = settings.OPEN_METEO_TIMEZONE,
    timeout_s: int = settings.OPEN_METEO_TIMEOUT_S,
) -> Dict[str, Any]:
    """
    Chama a API do Open-Meteo e retorna o JSON **bruto** (sem normalizar/persistir).

    Parâmetros:
      - lat, lon: coordenadas
      - start_date: data inicial (YYYY-MM-DD)
      - days: quantidade de dias (1..14)
      - timezone: ex. 'UTC' (default configurado - Porto)
      - timeout_s: segundos para timeout HTTP

    Retorna:
      - dict com a resposta do provider (contendo 'daily', 'timezone', etc.)

    Erros:
      - OpenMeteoHttpError: quando status HTTP não é 2xx ou rede falha.
    """
    if not (1 <= days <= 14):
        raise ValueError("days must be between 1 and 14")

    # calculo do end_date:
    end_date = date.fromordinal(start_date.toordinal() + (days - 1))

    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": settings.OPEN_METEO_DAILY_PARAMS,
        "timezone": timezone,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(OPEN_METEO_BASE_URL, params=params)
            resp.raise_for_status()
            return resp.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        raise OpenMeteoHttpError(f"Open-Meteo request failed: {e}") from e
