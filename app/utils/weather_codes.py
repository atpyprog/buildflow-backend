# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from typing import Optional

"""
Mapeamento e descrição de códigos meteorológicos.


- `WEATHER_CODE_MAP` traduz códigos → texto legível.
- `describe_weather(code)` devolve a descrição humana (ex.: "Chuva forte").
- Tabela compacta baseada nos códigos Open-Meteo: https://open-meteo.com/en/docs
"""

WEATHER_CODE_MAP = {
    0:  "Céu limpo",
    1:  "Principalmente limpo",
    2:  "Parcialmente nublado",
    3:  "Nublado",
    45: "Nevoeiro",
    48: "Nevoeiro depositante",
    51: "Garoa leve",
    53: "Garoa moderada",
    55: "Garoa intensa",
    56: "Garoa congelante leve",
    57: "Garoa congelante intensa",
    61: "Chuva fraca",
    63: "Chuva moderada",
    65: "Chuva forte",
    66: "Chuva congelante fraca",
    67: "Chuva congelante forte",
    71: "Neve fraca",
    73: "Neve moderada",
    75: "Neve forte",
    77: "Grãos de neve",
    80: "Aguaceiros fracos",
    81: "Aguaceiros moderados",
    82: "Aguaceiros fortes",
    85: "Aguaceiros de neve fracos",
    86: "Aguaceiros de neve fortes",
    95: "Trovoada",
    96: "Trovoada com granizo fraco",
    99: "Trovoada com granizo forte",
}

def describe_weather(code: int | None) -> Optional[str]:
    if code is None:
        return None
    return WEATHER_CODE_MAP.get(int(code), f"Código {code}")
