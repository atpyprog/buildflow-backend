# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from datetime import date
from typing import Any, Dict, List, Tuple

"""
Normalização do payload Open‑Meteo (semana/dia) para estrutura interna.


- Valida listas, converte e padroniza campos (target_date, weather_code, temp_min/max, precip_mm, wind_kmh).
- Lança `WeatherNormalizationError` em inconsistências.
- `normalize_week_payload()` retorna lista de dicionários normalizados.
"""


class WeatherNormalizationError(ValueError):
    """Erro de normalização do payload do Open-Meteo."""


def _expect_list(d: Dict[str, Any], key: str) -> List[Any]:
    """
    Garante que a chave existe e é uma lista (o Open-Meteo sempre retorna listas em 'daily').
    """
    v = d.get(key)
    if not isinstance(v, list):
        raise WeatherNormalizationError(f"Expected list for '{key}', got: {type(v).__name__}")
    return v


def normalize_week_payload(
    raw: Dict[str, Any],
    expect_start: date,
    expect_days: int,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Converte o JSON bruto do Open-Meteo em uma lista de dicts por dia.

    Entrada:
      - raw: dict retornado pelo client (Open-Meteo)
      - expect_start: data inicial esperada (para sanity check)
      - expect_days: total de dias esperados (1..14)

    Saída:
      - (days, timezone)
        days = [
          {
            "target_date": date,
            "weather_code": int|None,
            "temp_min_c": float|None,
            "temp_max_c": float|None,
            "precipitation_mm": float|None,
            "wind_kmh": float|None,
          },
          ...
        ]
        timezone = string (ex.: "UTC")
    """
    if "daily" not in raw:
        raise WeatherNormalizationError("Missing 'daily' key in provider response")

    daily = raw["daily"]

    times = _expect_list(daily, "time")
    wcode = _expect_list(daily, "weathercode")
    tmax = _expect_list(daily, "temperature_2m_max")
    tmin = _expect_list(daily, "temperature_2m_min")
    prec = _expect_list(daily, "precipitation_sum")
    wind = _expect_list(daily, "windspeed_10m_max")

    n = len(times)
    if n == 0:
        return [], raw.get("timezone", "UTC")

    if not all(len(arr) == n for arr in (wcode, tmax, tmin, prec, wind)):
        raise WeatherNormalizationError("Daily arrays have inconsistent lengths")

    out: List[Dict[str, Any]] = []
    for i in range(n):
        day = date.fromisoformat(times[i])

        out.append({
            "target_date": day,
            "weather_code": int(wcode[i]) if wcode[i] is not None else None,
            "temp_min_c": float(tmin[i]) if tmin[i] is not None else None,
            "temp_max_c": float(tmax[i]) if tmax[i] is not None else None,
            "precipitation_mm": float(prec[i]) if prec[i] is not None else None,
            "wind_kmh": float(wind[i]) if wind[i] is not None else None,
        })

    tz = raw.get("timezone", "UTC")
    return out, tz
