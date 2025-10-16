# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

"""
Motor de avaliação de regras climáticas.


- Comparadores e agregações (sum/avg/max/min/count).
- Avaliação por dia (`eval_rule_per_day`) e por janela (`eval_rule_rolling`).
- `evaluate_rules()` produz ações planejadas (ex.: create_issue) a partir de matches.
- Suporta escopos e descrição/sugestão para templates de issues.
"""

Number = float | int

def _fmt(val: Any) -> str:
    return "" if val is None else str(val)

def render_tmpl(tmpl: str, ctx: Dict[str, Any]) -> str:
    out = tmpl
    for k, v in ctx.items():
        out = out.replace("{"+k+"}", _fmt(v))
    return out

# leitura segura de métricas
_METRICS = {"weather_code", "temp_min_c", "temp_max_c", "precipitation_mm", "wind_kmh"}

def get_metric(day: Dict[str, Any], name: str) -> Optional[Number]:
    if name not in _METRICS:
        return None
    return day.get(name)

# comparadores
def cmp_value(op: str, actual: Any, value: Any) -> bool:
    if actual is None:
        return False
    if op in (">", ">=", "<", "<=", "=="):
        try:
            a = float(actual)
            b = float(value)
        except Exception:
            return False
        if op == ">":  return a > b
        if op == ">=": return a >= b
        if op == "<":  return a < b
        if op == "<=": return a <= b
        if op == "==": return a == b
    elif op == "in":
        try:
            return actual in value
        except Exception:
            return False
    elif op == "between":
        try:
            lo, hi = value
            a = float(actual)
            return float(lo) <= a <= float(hi)
        except Exception:
            return False
    return False

# avaliação de 1 regra (per_day)
def eval_rule_per_day(rule: Dict[str, Any], day: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    when_horizon_max = rule.get("when_horizon_max")
    if when_horizon_max is not None and isinstance(day.get("forecast_horizon_days"), int):
        if day["forecast_horizon_days"] > int(when_horizon_max):
            return None

    metric = rule["metric"]
    op     = rule["op"]
    value  = rule.get("value")
    actual = get_metric(day, metric)

    if not cmp_value(op, actual, value):
        return None

    # match
    return {
        "rule_id": rule.get("id"),
        "rule_name": rule.get("name"),
        "severity": rule.get("severity", "medium"),
        "evidence": {
            "metric": metric, "op": op, "value": value,
            "actual": actual, "aggregate": None
        }
    }

# rolling window (sum/avg/max/min/count)
def agg_block(vals: List[Optional[Number]], agg: str) -> Optional[Number]:
    arr = [float(v) for v in vals if v is not None]
    if len(arr) == 0:
        return None
    if agg == "sum":
        return sum(arr)
    if agg == "avg":
        return sum(arr) / len(arr)
    if agg == "max":
        return max(arr)
    if agg == "min":
        return min(arr)
    if agg == "count":
        return float(len(arr))
    return None

def eval_rule_rolling(rule: Dict[str, Any], days: List[Dict[str, Any]]) -> List[Tuple[int, Dict[str, Any]]]:
    window_days = int(rule["window_days"])
    aggregate   = rule["aggregate"]
    metric      = rule["metric"]
    op          = rule["op"]
    value       = rule.get("value")

    matches: List[Tuple[int, Dict[str, Any]]] = []
    for i in range(len(days)):
        block = days[i:i+window_days]
        if len(block) < window_days:
            break

        wh = rule.get("when_horizon_max")
        if wh is not None:
            if any((d.get("forecast_horizon_days", 999) > int(wh)) for d in block):
                continue

        vals = [get_metric(d, metric) for d in block]
        agg_val = agg_block(vals, aggregate)
        if agg_val is None:
            continue

        if cmp_value(op, agg_val, value):
            matches.append((i+window_days-1, {
                "rule_id": rule.get("id"),
                "rule_name": rule.get("name"),
                "severity": rule.get("severity", "medium"),
                "evidence": {
                    "metric": metric, "op": op, "value": value,
                    "actual": agg_val, "aggregate": f"{aggregate}({window_days})"
                }
            }))
    return matches

# Engine principal
def evaluate_rules(
    sector_id: str,
    days: List[Dict[str, Any]],
    rules: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Retorna estrutura com matches por dia e ações planejadas (create_issue).
    Não toca no banco; apenas prepara "planned".
    """
    planned_actions: List[Dict[str, Any]] = []
    days_out: List[Dict[str, Any]] = []

    # mapa target_date -> index
    idx_by_date = {d["target_date"]: i for i, d in enumerate(days)}

    for i, day in enumerate(days):
        day_matches: List[Dict[str, Any]] = []

        for rule in rules:
            scope = rule.get("scope", "per_day")

            if scope == "per_day":
                m = eval_rule_per_day(rule, day)
                if not m:
                    continue
                day_matches.append(m)

                if rule.get("auto_actions", {}).get("create_issue", True):
                    ctx = {**day, "sector_id": sector_id}
                    title = rule.get("suggest", {}).get("title", rule.get("name", "Issue gerada por regra"))
                    desc_tmpl = rule.get("suggest", {}).get("description_tmpl", "")
                    desc = render_tmpl(desc_tmpl, ctx)
                    dedupe_tmpl = rule.get("dedupe_key_tmpl", "issue:{sector_id}:{target_date}:{name}")
                    dedupe_key = render_tmpl(dedupe_tmpl, {**ctx, "name": rule.get("name","rule")})
                    planned_actions.append({
                        "type": "create_issue",
                        "target": {"sector_id": sector_id, "date": day["target_date"]},
                        "title": title,
                        "description": desc,
                        "severity": rule.get("severity", "medium"),
                        "category": "weather",
                        "dedupe_key": dedupe_key,
                        "rule_id": rule.get("id")
                    })

            elif scope == "rolling":
                for end_idx, m in eval_rule_rolling(rule, days):
                    if end_idx == i:
                        day_matches.append(m)
                        if rule.get("auto_actions", {}).get("create_issue", True):
                            ctx = {**day, "sector_id": sector_id}
                            title = rule.get("suggest", {}).get("title", rule.get("name", "Issue gerada por regra"))
                            desc_tmpl = rule.get("suggest", {}).get("description_tmpl", "")
                            desc = render_tmpl(desc_tmpl, ctx)
                            dedupe_tmpl = rule.get("dedupe_key_tmpl", "issue:{sector_id}:{target_date}:{name}")
                            dedupe_key = render_tmpl(dedupe_tmpl, {**ctx, "name": rule.get("name","rule")})
                            planned_actions.append({
                                "type": "create_issue",
                                "target": {"sector_id": sector_id, "date": day["target_date"]},
                                "title": title,
                                "description": desc,
                                "severity": rule.get("severity", "medium"),
                                "category": "weather",
                                "dedupe_key": dedupe_key,
                                "rule_id": rule.get("id")
                            })

        days_out.append({
            "target_date": day["target_date"],
            "values": {
                "weather_code": day.get("weather_code"),
                "temp_min_c": day.get("temp_min_c"),
                "temp_max_c": day.get("temp_max_c"),
                "precipitation_mm": day.get("precipitation_mm"),
                "wind_kmh": day.get("wind_kmh"),
                "forecast_horizon_days": day.get("forecast_horizon_days", 0),
            },
            "matches": day_matches
        })

    return {
        "days": days_out,
        "actions": {"planned": planned_actions, "committed": [], "skipped": []},
    }
