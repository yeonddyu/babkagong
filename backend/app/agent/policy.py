"""밥카공 추천 정책 (초기값). 기상청 공식 추천 기준이 아니며 환경변수로 조정할 수 있다."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class WeatherPolicy:
    cold_temp_c: float = field(default_factory=lambda: _f("POLICY_COLD_TEMP_C", 5))
    hot_temp_c: float = field(default_factory=lambda: _f("POLICY_HOT_TEMP_C", 28))
    rain_pop_percent: float = field(default_factory=lambda: _f("POLICY_RAIN_POP", 60))
    warm_bonus: float = 10
    cold_bonus: float = 10
    rain_distance_weight: float = 2.0  # 비 올 때 거리 감점 배율
    # 메뉴명 키워드로만 온열/냉 음식을 판단한다. 키워드에 없으면 중립 (임의 분류 금지)
    warm_keywords: tuple[str, ...] = ("찌개", "탕", "국밥", "전골", "칼국수", "라멘", "우동", "샤브", "짬뽕", "해장국", "순대국", "곰탕", "설렁탕", "수제비", "훠궈", "나베", "국수전골")
    cold_keywords: tuple[str, ...] = ("냉면", "메밀", "소바", "물회", "콩국수", "냉모밀", "냉우동", "빙수", "냉국", "비빔국수")


@dataclass(frozen=True)
class CoursePolicy:
    meal_minutes: int = 60  # 식사 소요 시간 가정 (역산 기준용)
    min_cafe_minutes: int = 60  # 카공 최소 시간 가정
    cafe_radius_m: int = 500
    cafe_radius_short_walk_m: int = 300
    distance_penalty_per_m: float = 1 / 20  # 기본 거리 감점 (20m 당 1점)
    short_walk_weight: float = 2.0


WEATHER_POLICY = WeatherPolicy()
COURSE_POLICY = CoursePolicy()
