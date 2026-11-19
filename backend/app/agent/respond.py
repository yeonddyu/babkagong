"""F3011 최종 응답 생성.

응답 = 추천 항목(식당) + 보조 정보(카페) + 판단 기준 + 근거 Tool 결과 + 제외 사유 + 안내.
문장은 구조화된 결과만으로 만든다. LLM 이 있으면 같은 JSON 만 근거로 문장을 다듬고, 없거나 실패하면 템플릿을 쓴다.
사용자 화면에는 API 키·내부 예외 상세를 넣지 않는다 (NF3002).
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

from app.agent.conditions import AnalysisResult, Conditions
from app.agent.execution import ExecutionData, ToolExecutor
from app.agent.judge import Evaluation, RestaurantEvaluation
from app.agent.planning import Plan
from app.tools.nearby_cafes import WALK_BASIS, estimate_walk_minutes

logger = logging.getLogger(__name__)

HEALTH_DISCLAIMER = "알레르기·질환·식단 관련 판단은 전문가 조언을 대신하지 않습니다. 메뉴 재료와 조리 방식은 매장에 직접 확인하세요."
CAFE_UNVERIFIED = "카페 영업시간·콘센트·와이파이·혼잡도는 외부 데이터로 확인할 수 없어 방문 전 확인이 필요합니다."

TOOL_LABEL = {
    "search_restaurant_candidates": "음식점 후보 조회",
    "get_restaurant_details": "음식점 상세정보 조회",
    "search_nearby_cafes": "주변 카페 검색",
    "get_weather_context": "날씨 조회",
}
CODE_NOTICE = {
    "MISSING_API_KEY": "API 키가 설정되지 않아 확인하지 못했습니다",
    "TIMEOUT": "외부 서비스 응답이 늦어 확인하지 못했습니다",
    "API_ERROR": "외부 서비스 오류로 확인하지 못했습니다",
    "NO_RESULT": "조건에 맞는 결과가 없었습니다",
    "INVALID_INPUT": "입력값 문제로 확인하지 못했습니다",
}

HELP_TEXT = (
    "밥카공은 강남역·역삼역 주변에서 식사할 곳과 식사 후 카공할 카페를 함께 추천해요.\n"
    "• 예: \"강남역에서 1만 5천원 이하로 12시에 점심 먹고 카공할래\"\n"
    "• 조건: 날짜·시각, 음식 종류, 예산, 가까운 곳 선호, 몇 m/몇 분 이내\n"
    "• 후속: \"같은 조건에서 한식 말고 일식으로\", \"이 코스로 저장해줘\"\n"
    "메뉴 가격·영업시간은 서울관광재단 데이터로 확인된 경우만 사용하고, 날씨는 기상청 예보를 반영해요."
)


def _won(v: int | None) -> str:
    return f"{v:,}원" if v else "가격 미확인"


def _restaurant_view(rec: dict[str, Any]) -> dict[str, Any]:
    r, e = rec["restaurant"], rec["evaluation"]
    e: RestaurantEvaluation
    walk = estimate_walk_minutes(r.get("distance_m"))
    return {
        "name": r["name"], "source": r["source"], "source_id": r["source_id"],
        "address": r.get("road_address") or r.get("jibun_address"),
        "latitude": r.get("latitude"), "longitude": r.get("longitude"),
        "category": r.get("category"), "food_type": r.get("food_type"),
        "area": r.get("searched_area"),
        "distance_m": r.get("distance_m"), "distance_basis": "역 중심 직선거리",
        "estimated_walk_minutes": walk,
        "matched_menus": [{"name": m["name"], "price_krw": m.get("price_krw")} for m in rec["matched_menus"]],
        "business_hours": rec.get("business_hours"),
        "checks": [asdict(c) for c in e.checks],
        "score": e.score, "score_reasons": e.score_reasons,
        "unverified": e.warnings,
    }


def _cafe_view(c: dict[str, Any]) -> dict[str, Any]:
    return {k: c.get(k) for k in ("name", "source", "source_id", "road_address", "address", "latitude", "longitude",
                                  "distance_m", "distance_basis", "estimated_walk_minutes", "place_url", "phone")}


def _notices(ex: ToolExecutor | None) -> list[str]:
    notices: list[str] = []
    seen = set()
    for call in (ex.calls if ex else []):
        if call.ok or call.error_code in (None, "NO_RESULT") or call.reused:
            continue
        key = (call.tool, call.error_code)
        if key in seen:
            continue
        seen.add(key)
        notices.append(f"{TOOL_LABEL.get(call.tool, call.tool)}: {CODE_NOTICE.get(call.error_code, '확인하지 못했습니다')}")
    return notices


def _weather_mismatch(analysis: AnalysisResult, data: ExecutionData | None) -> list[str]:
    said = analysis.user_reported_weather
    if not said or not data or not data.weather:
        return []
    from app.agent.judge import is_rainy

    w = data.weather
    if said in ("비", "눈") and not is_rainy(w):
        return [f"말씀하신 날씨({said})와 달리 기상청 예보는 강수확률 {w.get('precipitation_probability')}%·{w.get('precipitation_type')}예요. "
                "가까운 곳 선호는 그대로 반영했어요."]
    return []


def _suggestions(conditions: Conditions) -> list[str]:
    out = []
    if conditions.constraint.budget_max:
        out.append(f"예산을 {conditions.constraint.budget_max + 5000:,}원 정도로 올려 보기")
    if conditions.preference.food_type:
        out.append(f"음식 종류({conditions.preference.food_type}) 조건 빼 보기")
    if conditions.constraint.max_walk_m or conditions.constraint.max_walk_minutes:
        out.append("거리 조건 완화하기")
    if conditions.base.meal_time:
        out.append("식사 시각 바꿔 보기")
    out.append("가격·영업시간이 확인된 식당이 적어서, 조건을 줄이면 더 많은 후보를 판단할 수 있어요")
    return out


def _weather_view(data: ExecutionData | None) -> dict[str, Any] | None:
    if not data or not data.weather:
        return None
    w = data.weather
    return {k: w.get(k) for k in ("forecast_datetime", "base_datetime", "temperature_c", "precipitation_probability",
                                  "precipitation_type", "sky", "default_applied", "notes")}


def _template_message(intent: str, body: dict[str, Any]) -> str:
    if intent == "smalltalk":
        return "안녕하세요! 밥카공이에요. 강남역·역삼역에서 식사하고 카공할 곳을 함께 추천해 드릴게요. 어디서 무엇을 드시고 싶은지 말씀해 주세요."
    if intent == "help":
        return HELP_TEXT
    if intent == "save_plan":
        sr = body.get("save_result") or {}
        if not sr.get("ok"):
            return sr.get("reason", "계획을 저장하지 못했습니다.")
        p = sr["plan"]
        lines = [f"계획을 저장했어요: {p['title']} — {p['plan_date']} {p['start_time'][:5]}~{p['end_time'][:5]}"]
        for a in sr.get("assumptions", []):
            lines.append(f"ℹ {a}")
        if sr.get("conflicts"):
            lines.append("⚠ 같은 날 시간이 겹치는 계획이 있어요 (저장은 완료): " +
                         ", ".join(f"{c['title']}({c['start_time'][:5]}~{c['end_time'][:5]})" for c in sr["conflicts"]))
        return "\n".join(lines)
    if intent == "out_of_scope":
        return "저는 강남역·역삼역 주변 식사 장소와 카공 카페 추천만 도와드릴 수 있어요. 예: \"역삼역 1만원 이하 점심 먹고 카공\""
    if body.get("clarify"):
        return "어느 지역에서 찾을까요? 강남역 또는 역삼역 중에서 골라 주세요. (화면 위 지역 선택을 사용해도 돼요)"
    lines: list[str] = []
    recs = body["recommendations"]
    w = body.get("weather")
    if w:
        lines.append(f"🌤 {w['forecast_datetime'][5:16].replace('T', ' ')} 예보: {w['temperature_c']}°C, 강수확률 {w['precipitation_probability']}% ({w['precipitation_type']})")
    if recs:
        lines.append(f"조건에 맞는 코스 {len(recs)}개를 찾았어요.")
        for i, r in enumerate(recs, 1):
            menu = ", ".join(f"{m['name']} {_won(m['price_krw'])}" for m in r["matched_menus"][:2])
            line = f"{i}. {r['name']} — 역에서 직선 {r['distance_m']}m(도보 약 {r['estimated_walk_minutes']}분 추정)"
            if menu:
                line += f", 메뉴 예: {menu}"
            if r["business_hours"]:
                line += f", 영업 {r['business_hours']}"
            lines.append(line)
            if r["cafes"]:
                c = r["cafes"][0]
                lines.append(f"   ☕ 식당에서 직선 {c['distance_m']}m: {c['name']}" + (f" ({c['place_url']})" if c.get("place_url") else ""))
            elif r.get("cafe_notice"):
                lines.append(f"   ☕ {r['cafe_notice']}")
            for u in r["unverified"][:2]:
                lines.append(f"   ⚠ {u}")
        lines.append(CAFE_UNVERIFIED)
    else:
        lines.append("조건을 모두 만족하는 식당을 찾지 못했어요.")
        if body.get("stop_reason"):
            lines.append(f"사유: {body['stop_reason']}")
        if body["excluded"]:
            lines.append("제외한 예: " + "; ".join(f"{x['name']}({x['reason']})" for x in body["excluded"][:3]))
        if body.get("suggestions"):
            lines.append("이렇게 바꿔 보시겠어요? " + " / ".join(body["suggestions"][:3]))
    for n in body.get("notices", []):
        lines.append(f"ℹ {n}")
    if body.get("disclaimer"):
        lines.append(body["disclaimer"])
    return "\n".join(lines)


LLM_PROMPT = """아래 JSON 은 밥카공 Agent 가 외부 API 와 코드 계산으로 확정한 결과다.
이 JSON 에 있는 사실만 사용해 한국어로 4~10줄 추천 메시지를 써라. 새 가격·영업시간·거리·편의시설을 만들지 말고,
추천 순서와 제외 사유를 바꾸지 마라. '추정'·'미확인' 표시는 그대로 유지하라."""


def build_response(
    analysis: AnalysisResult,
    conditions: Conditions,
    plan: Plan | None,
    data: ExecutionData | None,
    ev: Evaluation | None,
    ex: ToolExecutor | None,
    replans: list[dict[str, Any]],
    stop_reason: str | None,
    changed_fields: list[str],
    llm: Any | None = None,
    save_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recs_raw = []
    if data and ev:
        by_key = {f"{c['source']}:{c['source_id']}": c for c in data.candidates}
        for e in ev.satisfied[:3]:
            detail = data.details.get(e.key) or {}
            cafe_data = data.cafes.get(e.key) or {}
            cafe_err = data.cafe_errors.get(e.key)
            recs_raw.append({
                "restaurant": by_key[e.key], "evaluation": e, "matched_menus": e.matched_menus,
                "business_hours": (detail.get("operation") or {}).get("business_hours"),
                "cafes": cafe_data.get("cafes", []),
                "cafe_notice": (f"주변 카페: {CODE_NOTICE.get(cafe_err['code'], '확인하지 못했습니다')}" if cafe_err else None),
            })
    recommendations = []
    for raw in recs_raw:
        view = _restaurant_view(raw)
        view["cafes"] = [_cafe_view(c) for c in raw["cafes"][:3]]
        view["cafe_notice"] = raw["cafe_notice"]
        recommendations.append(view)

    filled = conditions.filled_fields()
    missing = [f for f in ("base.visit_date", "base.meal_time", "preference.food_type", "constraint.budget_max")
               if f not in filled]
    body: dict[str, Any] = {
        "intent": analysis.intent,
        "intent_reason": analysis.reason,
        "decided_by": analysis.decided_by,
        "conditions": {**conditions.model_dump(mode="json"), "missing": missing, "changed": changed_fields},
        "plan": plan.model_dump(mode="json") if plan else None,
        "clarify": bool(plan and plan.mode == "clarify"),
        "weather": _weather_view(data),
        "weather_policy": ev.weather_applied if ev else [],
        "recommendations": recommendations,
        "excluded": [{"name": e.name, "source": e.source, "source_id": e.source_id, "reason": e.excluded_reason}
                     for e in (ev.excluded if ev else [])],
        "criteria": (ev.criteria if ev else []) + ([f"도보 시간: {WALK_BASIS}"] if recommendations else []),
        "evidence": [{"seq": c.seq, "tool": c.tool, "label": TOOL_LABEL.get(c.tool, c.tool), "ok": c.ok,
                      "error_code": c.error_code, "summary": c.summary if c.ok else CODE_NOTICE.get(c.error_code or "", "실패"),
                      "duration_ms": c.duration_ms, "reused": c.reused} for c in (ex.calls if ex else [])],
        "replans": replans,
        "stop_reason": stop_reason,
        "suggestions": _suggestions(conditions) if (ev is not None and not recommendations) else [],
        "notices": _notices(ex) + _weather_mismatch(analysis, data),
        "disclaimer": HEALTH_DISCLAIMER if analysis.mentions_health else None,
        "query_basis": (data.candidate_meta or {}).get("query_basis") if data else None,
        "saved_plan": (save_result or {}).get("plan"),
        "plan_conflicts": (save_result or {}).get("conflicts", []),
        "save_result": save_result,
    }
    body["message"] = _template_message(analysis.intent, body)
    body["message_by"] = "template"
    if llm is not None and recommendations:
        try:
            facts = {k: body[k] for k in ("weather", "recommendations", "excluded", "criteria", "notices", "disclaimer")}
            out = llm.invoke([("system", LLM_PROMPT), ("human", json.dumps(facts, ensure_ascii=False, default=str))])
            text = getattr(out, "content", None)
            if isinstance(text, str) and text.strip():
                body["message"] = text.strip()
                body["message_by"] = "llm"
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM 응답 생성 실패, 템플릿 사용: %s", type(exc).__name__)
    return body
