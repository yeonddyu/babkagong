"""저장할 코스 구성 (F3015): 직전 추천 요약 + 조건으로 계획 값을 만든다.

시각이 요청에 없으면 정책 기본값을 쓰고 그 사실을 assumptions 로 알린다.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from app.agent.conditions import Conditions
from app.agent.execution import PERIOD_REFERENCE_TIME
from app.agent.policy import COURSE_POLICY
from app.storage.plans import PlanCreate

DEFAULT_START = time(12, 0)
DEFAULT_CAFE_MINUTES = 120


def course_from_memory(previous: dict[str, Any], index: int, today: date, session_id: str | None,
                       cafe_index: int = 0) -> dict[str, Any] | None:
    recs = previous.get("recommendations") or []
    if not recs or not (0 <= index < len(recs)):
        return None
    rec = recs[index]
    cond = Conditions.model_validate(previous.get("conditions") or {})
    assumptions: list[str] = []
    day = cond.base.visit_date
    if day is None:
        day = today
        assumptions.append(f"날짜를 말하지 않아 오늘({today.isoformat()})로 저장했어요.")
    start = cond.base.meal_time
    if start is None:
        start = PERIOD_REFERENCE_TIME.get(cond.base.meal_period or "", DEFAULT_START)
        assumptions.append(f"식사 시각을 말하지 않아 {start.strftime('%H:%M')} 시작으로 저장했어요.")
    if cond.constraint.end_by and cond.constraint.end_by > start:
        end = cond.constraint.end_by
    else:
        end_dt = datetime.combine(day, start) + timedelta(minutes=COURSE_POLICY.meal_minutes + DEFAULT_CAFE_MINUTES)
        end = end_dt.time() if end_dt.date() == day else time(23, 59)
        assumptions.append(f"종료 시각은 식사 {COURSE_POLICY.meal_minutes}분 + 카공 {DEFAULT_CAFE_MINUTES}분 기준 {end.strftime('%H:%M')}로 저장했어요. 계획 화면에서 수정할 수 있어요.")
    r = rec["restaurant"]
    cafes = rec.get("cafes") or []
    if not 0 <= cafe_index < len(cafes):
        cafe_index = 0
    cafe = cafes[cafe_index] if cafes else {}
    plan = PlanCreate(
        title=f"{r['name']}" + (f" + {cafe['name']}" if cafe.get("name") else ""),
        plan_date=day, start_time=start, end_time=end, area=r.get("area") or cond.preference.area,
        restaurant_name=r["name"], restaurant_source=r.get("source"), restaurant_source_id=r.get("source_id"),
        restaurant_address=r.get("address"), restaurant_lat=r.get("latitude"), restaurant_lng=r.get("longitude"),
        cafe_name=cafe.get("name"), cafe_source=cafe.get("source"), cafe_lat=cafe.get("latitude"), cafe_lng=cafe.get("longitude"),
        cafe_source_id=cafe.get("source_id"), cafe_address=cafe.get("road_address") or cafe.get("address"),
        cafe_url=cafe.get("place_url"), session_id=session_id,
    )
    return {"plan": plan, "assumptions": assumptions}
