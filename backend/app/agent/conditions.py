"""요청 조건 모델 (F3005). 추출하지 못한 값은 None 으로 남긴다."""
from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field

Area = Literal["강남역", "역삼역"]
FoodType = Literal["한식", "중식", "일식", "양식", "분식", "기타"]
MealPeriod = Literal["아침", "점심", "저녁"]
Intent = Literal["recommend", "smalltalk", "help", "save_plan", "out_of_scope"]


class BaseConditions(BaseModel):
    """계획의 기준이 되는 조건."""

    visit_date: date | None = Field(default=None, description="방문 날짜")
    meal_period: MealPeriod | None = Field(default=None, description="식사 구분 (아침/점심/저녁)")
    meal_time: time | None = Field(default=None, description="식사 시각")
    cafe_time: time | None = Field(default=None, description="카페 방문 시각")


class PreferenceConditions(BaseModel):
    """선호 조건."""

    area: Area | None = None
    food_type: FoodType | None = None
    exclude_food_types: list[FoodType] = Field(default_factory=list)
    prefer_short_walk: bool | None = Field(default=None, description="많이 걷기 싫음 / 가까운 곳 선호")


class ConstraintConditions(BaseModel):
    """제약 조건 (위반 시 제외)."""

    budget_max: int | None = Field(default=None, description="1인 메뉴 상한 금액(원)")
    max_walk_m: int | None = Field(default=None, description="역 기준 최대 직선거리(m)")
    max_walk_minutes: int | None = Field(default=None, description="최대 도보 시간(분)")
    end_by: time | None = Field(default=None, description="일정이 끝나야 하는 시각")


class Conditions(BaseModel):
    base: BaseConditions = Field(default_factory=BaseConditions)
    preference: PreferenceConditions = Field(default_factory=PreferenceConditions)
    constraint: ConstraintConditions = Field(default_factory=ConstraintConditions)

    def filled_fields(self) -> dict[str, object]:
        """값이 있는 필드만 'group.field' 키로 반환."""
        out: dict[str, object] = {}
        for group in ("base", "preference", "constraint"):
            for key, value in getattr(self, group).model_dump().items():
                if value not in (None, [], ""):
                    out[f"{group}.{key}"] = value
        return out

    def merged_with(self, updates: "Conditions") -> "Conditions":
        """updates 에 값이 있는 필드만 덮어쓴 새 조건 (F3010 후속 요청)."""
        data = self.model_dump()
        for path, value in updates.filled_fields().items():
            group, key = path.split(".")
            data[group][key] = value
        return Conditions.model_validate(data)


class AnalysisResult(BaseModel):
    intent: Intent
    reason: str = Field(description="의도 판단 이유")
    decided_by: Literal["llm", "rule"]
    conditions: Conditions = Field(default_factory=Conditions, description="이번 발화에서 명시된 조건만")
    is_followup: bool = Field(default=False, description="직전 조건을 이어받는 후속 요청인지")
    reset: bool = Field(default=False, description="이전 맥락을 버리고 새로 시작")
    mentions_health: bool = Field(default=False, description="알레르기·질환 등 건강 관련 언급")
    user_reported_weather: str | None = Field(default=None, description="사용자가 말한 날씨 (참고용, 판단은 기상청 값 사용)")
