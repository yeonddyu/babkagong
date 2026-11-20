"""F3006 작업 계획 수립.

요청 처리에 필요한 Tool 과 호출 순서를 코드 규칙으로 정한다 (모델 판단이 필요 없는 작업).
- 인사·사용법·범위 밖·저장 요청은 Tool 이 필요 없어 계획을 비운다.
- 지역이 없으면 거리 계산의 시작점이 없어 Tool 을 부르기 전에 되묻는다.
- 날씨 예보 범위(약 3일) 밖이면 날씨 Tool 을 계획에서 뺀다.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.conditions import AnalysisResult, Conditions

CANDIDATE_POOL = 30  # 후보 Tool 에 요청할 최대 후보 수
DETAIL_BATCH = 10  # 한 번에 상세정보를 조회할 후보 수 (캐시 사용으로 호출당 1ms 미만)
CAFE_TARGETS = 5  # 화면에 추천하고 주변 카페를 찾을 식당 수
CAFE_RADIUS_M = 500
CAFE_RADIUS_SHORT_WALK_M = 300
WEATHER_RANGE_DAYS = 3


class PlanStep(BaseModel):
    order: int
    tool: str
    purpose: str
    inputs_from: str = Field(description="입력값의 출처 (요청 분석 결과 / 앞 Tool 결과)")


class Plan(BaseModel):
    mode: Literal["tools", "skip", "clarify"]
    steps: list[PlanStep] = Field(default_factory=list)
    reason: str
    missing: list[str] = Field(default_factory=list, description="되물어야 할 조건")
    excluded_tools: list[dict[str, str]] = Field(default_factory=list, description="계획에서 뺀 Tool 과 이유")


def build_plan(analysis: AnalysisResult, conditions: Conditions, today: date) -> Plan:
    if analysis.intent != "recommend":
        return Plan(mode="skip", reason=f"의도가 '{analysis.intent}' 라 외부 Tool 호출이 필요 없음")

    if conditions.preference.area is None:
        return Plan(mode="clarify", reason="서비스 역(역삼·강남·언주·신논현·선릉·선정릉)이 정해지지 않아 거리 계산의 시작점이 없으므로 Tool 호출 전에 되물음",
                    missing=["area"])

    steps: list[PlanStep] = []
    excluded: list[dict[str, str]] = []
    visit = conditions.base.visit_date or today
    if visit < today:
        excluded.append({"tool": "get_weather_context", "reason": "지난 날짜는 단기예보로 확인할 수 없음"})
    elif visit > today + timedelta(days=WEATHER_RANGE_DAYS):
        excluded.append({"tool": "get_weather_context", "reason": f"방문일이 예보 범위({WEATHER_RANGE_DAYS}일)를 벗어남"})
    else:
        steps.append(PlanStep(order=0, tool="get_weather_context", purpose="방문 시각 날씨로 우선순위 가산점 계산",
                              inputs_from="요청 분석: area, visit_date, meal_time(없으면 식사 구분 기준 시각)"))
    steps.append(PlanStep(order=0, tool="search_restaurant_candidates", purpose=f"지역·음식 종류로 반경 안 음식점 후보 {CANDIDATE_POOL}곳을 거리 구간별로 고르게 확보 (메뉴 정보 있는 곳 우선)",
                          inputs_from="요청 분석: area, food_type, visit_date"))
    steps.append(PlanStep(order=0, tool="get_restaurant_details",
                          purpose=f"후보 중 가까운 {DETAIL_BATCH}곳의 메뉴·가격·영업시간 확인",
                          inputs_from="search_restaurant_candidates: candidates[].source, source_id"))
    steps.append(PlanStep(order=0, tool="search_nearby_cafes", purpose=f"조건을 충족한 식당 상위 {CAFE_TARGETS}곳 주변 카페 검색",
                          inputs_from="get_restaurant_details/후보: latitude, longitude (+ 날씨·도보 선호로 반경 결정)"))
    for i, step in enumerate(steps, start=1):
        step.order = i
    return Plan(mode="tools", steps=steps, excluded_tools=excluded,
                reason="추천 요청이고 지역이 있어 날씨→후보→상세→카페 순으로 계획")
