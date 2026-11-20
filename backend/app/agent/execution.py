"""F3007 Tool 호출 및 결과 통합.

- 계획에 따라 Tool 을 호출하고 결과를 (tool, args) 키로 보관한다 → 재계획 시 재사용 (F3009)
- 앞 Tool 결과(후보 source/source_id, 좌표)를 다음 Tool 입력으로 전달한다
- Tool 이 실패해도 사유를 기록하고 다음 단계로 진행한다 (NF3003)
"""
from __future__ import annotations

import math

import json
import time as _time
from dataclasses import dataclass, field
from datetime import date, time
from typing import Any, Callable

from app.agent.conditions import Conditions
from app.agent.planning import CANDIDATE_POOL, DETAIL_BATCH
from app.tools.nearby_cafes import WALK_DETOUR_FACTOR, WALK_SPEED_M_PER_MIN
from app.tools.restaurant_candidates import SEARCH_RADIUS_M
from app.tools.registry import ToolRegistry

PERIOD_REFERENCE_TIME = {"아침": time(8, 0), "점심": time(12, 0), "저녁": time(18, 0)}

Emit = Callable[..., None]


def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


@dataclass
class ToolCallRecord:
    seq: int
    tool: str
    args: dict[str, Any]
    ok: bool
    error_code: str | None
    duration_ms: int
    reused: bool
    summary: str


@dataclass
class ToolExecutor:
    registry: ToolRegistry
    emit: Emit = _noop
    cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: list[ToolCallRecord] = field(default_factory=list)

    @staticmethod
    def key(tool: str, args: dict[str, Any]) -> str:
        return tool + ":" + json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)

    def call(self, tool: str, args: dict[str, Any], *, stage: str = "execute") -> dict[str, Any]:
        k = self.key(tool, args)
        if k in self.cache:
            result = self.cache[k]
            self.calls.append(ToolCallRecord(len(self.calls) + 1, tool, args, result["ok"],
                                             (result.get("error") or {}).get("code"), 0, True, "이전 결과 재사용"))
            self.emit("tool_reuse", stage=stage, tool=tool, args=args)
            return result
        self.emit("tool_call", stage=stage, tool=tool, args=args)
        start = _time.perf_counter()
        result = self.registry.invoke(tool, args)
        duration = int((_time.perf_counter() - start) * 1000)
        self.cache[k] = result
        summary = summarize_result(tool, result)
        code = (result.get("error") or {}).get("code")
        self.calls.append(ToolCallRecord(len(self.calls) + 1, tool, args, result["ok"], code, duration, False, summary))
        self.emit("tool_result", stage=stage, tool=tool, ok=result["ok"], error_code=code,
                  error_message=(result.get("error") or {}).get("message"), duration_ms=duration, summary=summary)
        return result

    @property
    def fresh_call_count(self) -> int:
        return sum(1 for c in self.calls if not c.reused)


def summarize_result(tool: str, result: dict[str, Any]) -> str:
    """원본 응답 대신 남길 한 줄 요약."""
    if not result["ok"]:
        return f"실패 {result['error']['code']}: {result['error']['message']}"
    d = result["data"]
    if tool == "search_restaurant_candidates":
        per_source = ", ".join("%s=%s" % (s["source"], s["returned"]) for s in d["source_status"])
        return f"후보 {len(d['candidates'])}곳 ({per_source})"
    if tool == "get_restaurant_details":
        menus = d.get("menus")
        return f"{d['basic']['name']}: 메뉴 {len(menus) if menus is not None else '미확인'}개, 영업시간 {'있음' if (d.get('operation') or {}).get('business_hours') else '미확인'}"
    if tool == "search_nearby_cafes":
        return f"카페 {len(d['cafes'])}곳 (총 {d['total_count']})"
    if tool == "get_weather_context":
        return f"{d['forecast_datetime'][:16]} 기온 {d['temperature_c']}°C, 강수확률 {d['precipitation_probability']}%, {d['precipitation_type']}"
    return "성공"


@dataclass
class ExecutionData:
    """실행 단계 사이에 전달하는 통합 결과 (Tool 이름별로 정리)."""

    weather: dict[str, Any] | None = None
    weather_error: dict[str, str] | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    candidate_meta: dict[str, Any] | None = None
    candidate_error: dict[str, str] | None = None
    details: dict[str, dict[str, Any]] = field(default_factory=dict)  # "source:source_id" → data
    detail_errors: dict[str, dict[str, str]] = field(default_factory=dict)
    detailed_count: int = 0  # 상세 조회를 시도한 후보 수 (다음 묶음 시작 위치)
    cafes: dict[str, dict[str, Any]] = field(default_factory=dict)  # 식당 키 → 카페 Tool data
    cafe_errors: dict[str, dict[str, str]] = field(default_factory=dict)
    areas_searched: list[str] = field(default_factory=list)


def cand_key(c: dict[str, Any]) -> str:
    return f"{c['source']}:{c['source_id']}"


def weather_args(conditions: Conditions, area: str, today: date) -> dict[str, Any]:
    args: dict[str, Any] = {"area": area}
    visit = conditions.base.visit_date
    if visit:
        args["visit_date"] = visit.isoformat()
    t = conditions.base.meal_time or PERIOD_REFERENCE_TIME.get(conditions.base.meal_period or "")
    if t:
        args["visit_time"] = t.strftime("%H:%M")
    return args


def run_weather(ex: ToolExecutor, data: ExecutionData, conditions: Conditions, area: str, today: date) -> None:
    r = ex.call("get_weather_context", weather_args(conditions, area, today))
    if r["ok"]:
        data.weather = r["data"]
    else:
        data.weather_error = r["error"]


def walk_limit_m(conditions: Conditions) -> int | None:
    """사용자가 말한 거리(m)·도보 시간(분) 제한을 역 중심 직선거리 상한으로 바꾼다.
    도보 시간은 판정과 같은 추정식(직선거리×우회계수÷보행속도)의 역산."""
    limits = []
    if conditions.constraint.max_walk_m:
        limits.append(conditions.constraint.max_walk_m)
    if conditions.constraint.max_walk_minutes:
        limits.append(math.floor(conditions.constraint.max_walk_minutes * WALK_SPEED_M_PER_MIN / WALK_DETOUR_FACTOR))
    return min(limits) if limits else None


def run_candidates(ex: ToolExecutor, data: ExecutionData, conditions: Conditions, area: str,
                   seed: int | None = None) -> None:
    # 가까운 순으로만 고르면 같은 지역은 늘 같은 식당이 나오므로, 반경 안에서 거리 구간별로 고르게 뽑는다.
    # seed 는 요청마다 바뀌고, 같은 seed 면 같은 후보 (실행 로그로 재현 가능)
    # 단, 걷기 싫다고 한 요청은 가까운 순을 유지한다 (다양성보다 사용자가 말한 조건이 우선).
    if conditions.preference.prefer_short_walk:
        args: dict[str, Any] = {"area": area, "max_results": CANDIDATE_POOL, "order": "distance"}
    else:
        args = {"area": area, "max_results": CANDIDATE_POOL, "order": "varied"}
        if seed is not None:
            args["seed"] = seed
    limit = walk_limit_m(conditions)
    if limit is not None:  # 거리·도보 시간 제한이 있으면 그 안에서만 고른다 (밖의 후보는 어차피 제외됨)
        args["radius_m"] = max(50, min(SEARCH_RADIUS_M, limit))
    if conditions.preference.food_type:
        args["food_type"] = conditions.preference.food_type
    if conditions.base.visit_date:
        args["reference_date"] = conditions.base.visit_date.isoformat()
    r = ex.call("search_restaurant_candidates", args)
    data.areas_searched.append(area)
    if not r["ok"]:
        data.candidate_error = r["error"]
        return
    excluded = set(conditions.preference.exclude_food_types)
    seen = {cand_key(c) for c in data.candidates}
    for c in r["data"]["candidates"]:
        if cand_key(c) not in seen and c.get("food_type") not in excluded:
            c = dict(c, searched_area=area)
            data.candidates.append(c)
    data.candidate_meta = {k: r["data"][k] for k in ("query_basis", "source_status", "radius_m", "area")}


def run_details(ex: ToolExecutor, data: ExecutionData, batch: int = DETAIL_BATCH) -> int:
    """다음 묶음 후보의 상세정보를 조회한다. 조회한 후보 수를 반환."""
    targets = data.candidates[data.detailed_count: data.detailed_count + batch]
    for c in targets:
        r = ex.call("get_restaurant_details", {"source": c["source"], "source_id": c["source_id"]})
        if r["ok"]:
            data.details[cand_key(c)] = r["data"]
        else:
            data.detail_errors[cand_key(c)] = r["error"]  # 사유 기록 후 다음 후보로 진행
    data.detailed_count += len(targets)
    return len(targets)


def run_cafes(ex: ToolExecutor, data: ExecutionData, restaurants: list[dict[str, Any]], radius_m: int) -> None:
    for c in restaurants:
        lat, lng = c.get("latitude"), c.get("longitude")
        if lat is None or lng is None:
            data.cafe_errors[cand_key(c)] = {"code": "INVALID_INPUT", "message": "식당 좌표가 없어 주변 카페를 찾지 않음"}
            continue
        r = ex.call("search_nearby_cafes", {"latitude": lat, "longitude": lng, "radius_m": radius_m, "max_results": 5})
        if r["ok"]:
            data.cafes[cand_key(c)] = r["data"]
        else:
            data.cafe_errors[cand_key(c)] = r["error"]
