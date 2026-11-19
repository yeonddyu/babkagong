"""F3008 제약 적합성 판단.

Tool 로 확보한 값으로만 계산·비교한다. 확인할 수 없는 값은 추정하지 않고 '판단 불가'로 두며,
확인할 수 있는 값에서 역산한 기준(예: 늦어도 몇 시에 식사를 시작해야 하는지)을 제시한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from app.agent.conditions import Conditions
from app.agent.execution import PERIOD_REFERENCE_TIME, ExecutionData, cand_key
from app.agent.policy import COURSE_POLICY, WEATHER_POLICY, CoursePolicy, WeatherPolicy
from app.tools.nearby_cafes import estimate_walk_minutes

Result = Literal["pass", "fail", "unknown"]
WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]


@dataclass
class Check:
    criterion: str
    result: Result
    value: str
    basis: str
    hard: bool  # True: fail/unknown 이면 제외 (사용자 제약)


@dataclass
class RestaurantEvaluation:
    key: str
    name: str
    source: str
    source_id: str
    status: Literal["satisfied", "excluded"]
    checks: list[Check]
    score: float
    score_reasons: list[str]
    excluded_reason: str | None
    matched_menus: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 영업시간 파싱
_SEG = re.compile(
    r"(?P<days>매일|평일|주말|[월화수목금토일](?:요일)?(?:\s*[~\-]\s*[월화수목금토일](?:요일)?)?(?:\s*,\s*[월화수목금토일](?:요일)?)*)?\s*"
    r"(?P<s>\d{1,2}:\d{2})\s*[~\-]\s*(?P<e>\d{1,2}:\d{2})"
)


def _days(spec: str | None) -> set[int]:
    if not spec or spec == "매일":
        return set(range(7))
    if spec == "평일":
        return {0, 1, 2, 3, 4}
    if spec == "주말":
        return {5, 6}
    names = re.findall(r"[월화수목금토일]", spec)
    if re.search(r"[~\-]", spec) and len(names) == 2:
        a, b = WEEKDAY_NAMES.index(names[0]), WEEKDAY_NAMES.index(names[1])
        return {(a + i) % 7 for i in range(((b - a) % 7) + 1)}
    return {WEEKDAY_NAMES.index(n) for n in names}


def _t(text: str) -> time | None:
    h, m = map(int, text.split(":"))
    if h == 24:
        h = 0
    return time(h, m) if 0 <= h <= 23 and 0 <= m <= 59 else None


def open_at(hours_text: str, weekday: int, at: time) -> tuple[Result, str]:
    """영업시간 원문으로 해당 요일·시각 영업 여부. 파싱할 수 없으면 unknown.

    쉼표·슬래시로 나눈 구간마다 해석한다. '공휴일' 구간은 공휴일 여부를 알 수 없어 쓰지 않고,
    '브레이크/휴게' 구간은 영업하지 않는 시간으로 본다.
    """
    segments, breaks = [], []
    for part in re.split(r"[,/\n]", hours_text):
        if "공휴일" in part:
            continue
        is_break = bool(re.search(r"브레이크|break|휴게|쉬는", part, re.IGNORECASE))
        for m in _SEG.finditer(part):
            s, e = _t(m.group("s")), _t(m.group("e"))
            if s and e:
                (breaks if is_break else segments).append((_days(m.group("days")), s, e))
    if not segments:
        return "unknown", "영업시간 형식을 해석할 수 없음"
    applicable = [(s, e) for days, s, e in segments if weekday in days]
    if not applicable:
        return "unknown", f"{WEEKDAY_NAMES[weekday]}요일 영업시간 정보 없음"

    def inside(s: time, e: time) -> bool:
        return (s <= at < e) if s < e else (at >= s or at < e)  # 자정 넘김

    for days, s, e in breaks:
        if weekday in days and inside(s, e):
            return "fail", f"{at.strftime('%H:%M')} 은 브레이크타임({s.strftime('%H:%M')}~{e.strftime('%H:%M')})"
    for s, e in applicable:
        if inside(s, e):
            return "pass", f"{s.strftime('%H:%M')}~{e.strftime('%H:%M')} 영업"
    ranges = ", ".join(f"{s.strftime('%H:%M')}~{e.strftime('%H:%M')}" for s, e in applicable)
    return "fail", f"{at.strftime('%H:%M')} 은 영업시간({ranges}) 밖"


def closed_on(holiday_text: str, day: date) -> Result:
    """휴무일 원문으로 방문일 휴무 여부. 공휴일 해당 여부는 판단하지 않는다."""
    text = holiday_text.replace(" ", "")
    if "연중무휴" in text or text in ("없음", "무휴"):
        return "pass"
    wd = day.weekday()
    if f"{WEEKDAY_NAMES[wd]}요일" in text or (wd >= 5 and "주말" in text) or (wd < 5 and "평일" in text):
        return "fail"
    if re.search(r"[월화수목금토일]요일|주말|평일", text):
        return "pass"  # 다른 요일만 휴무
    return "unknown"


# ---------------------------------------------------------------- 평가
MIN_MEAL_PRICE = 3000  # 이보다 싼 메뉴는 식사 메뉴로 보지 않음 (곁들임·데이터 오류 방지, 정책값)
SIDE_MENU = re.compile(r"추가|사리|공기밥|곱빼기|토핑|소스|음료|사이다|콜라|주류|소주|맥주|막걸리|와인|라떼|아메리카노|커피|에이드|주스|포장|세트\s*변경")


def is_meal_menu(menu: dict[str, Any], *, ignore_price: bool = False) -> bool:
    name = menu.get("name") or ""
    if SIDE_MENU.search(name):
        return False
    return ignore_price or (menu.get("price_krw") or 0) >= MIN_MEAL_PRICE



def reference_time(conditions: Conditions) -> tuple[time | None, str]:
    if conditions.base.meal_time:
        return conditions.base.meal_time, "요청한 식사 시각"
    if conditions.base.meal_period:
        t = PERIOD_REFERENCE_TIME[conditions.base.meal_period]
        return t, f"'{conditions.base.meal_period}' 기준 시각 {t.strftime('%H:%M')} (가정)"
    return None, ""


def is_rainy(weather: dict[str, Any] | None, policy: WeatherPolicy = WEATHER_POLICY) -> bool:
    if not weather:
        return False
    pop = weather.get("precipitation_probability")
    pty = weather.get("precipitation_type")
    return (pop is not None and pop >= policy.rain_pop_percent) or pty in ("비", "비/눈", "눈", "소나기")


def evaluate_restaurant(
    cand: dict[str, Any],
    detail: dict[str, Any] | None,
    detail_error: dict[str, str] | None,
    conditions: Conditions,
    weather: dict[str, Any] | None,
    visit_date: date,
    wpolicy: WeatherPolicy = WEATHER_POLICY,
    cpolicy: CoursePolicy = COURSE_POLICY,
) -> RestaurantEvaluation:
    checks: list[Check] = []
    warnings: list[str] = []
    matched: list[dict[str, Any]] = []
    budget = conditions.constraint.budget_max
    menus = (detail or {}).get("menus")
    operation = (detail or {}).get("operation") or {}

    if detail is None:
        why = (detail_error or {}).get("message", "상세정보를 조회하지 못함")
        warnings.append(f"상세정보 없음: {why}")
    elif not detail.get("detail_available"):
        warnings.append((detail.get("detail_unavailable") or {}).get("message", "상세정보 미제공 출처"))

    # 1) 예산 (제약)
    if budget is not None:
        priced = [m for m in (menus or []) if m.get("price_krw") and is_meal_menu(m)]
        within = sorted((m for m in priced if m["price_krw"] <= budget), key=lambda m: m["price_krw"])
        if within:
            matched = within
            checks.append(Check("예산", "pass", f"{budget:,}원 이하 메뉴 {len(within)}개 (최저 {within[0]['price_krw']:,}원)",
                                "레드테이블 메뉴정보 가격", True))
        elif priced and len(priced) == len([m for m in (menus or []) if is_meal_menu(m, ignore_price=True)]):
            low = min(m["price_krw"] for m in priced)
            checks.append(Check("예산", "fail", f"최저가 {low:,}원 > 예산 {budget:,}원", "레드테이블 메뉴정보 가격", True))
        else:
            checks.append(Check("예산", "unknown", f"가격 미확인 — {budget:,}원 이하 메뉴가 있는지 매장에서 확인 필요",
                                "메뉴·가격 정보 없음 (추정하지 않음)", True))

    # 2) 영업시간 (기준 시각)
    ref, ref_basis = reference_time(conditions)
    hours_text = operation.get("business_hours")
    if ref is not None:
        if hours_text:
            res, why = open_at(hours_text, visit_date.weekday(), ref)
            checks.append(Check("영업시간", res, why if res != "unknown" else f"{why} (원문: {hours_text})",
                                f"레드테이블 운영정보, {ref_basis}", res == "fail"))
        else:
            checks.append(Check("영업시간", "unknown", f"영업시간 미확인 — {ref.strftime('%H:%M')} 영업 여부를 방문 전 확인 필요",
                                "운영정보 없음 (추정하지 않음)", False))

    # 3) 휴무일
    holidays = operation.get("holidays")
    if holidays:
        res = closed_on(holidays, visit_date)
        checks.append(Check("휴무일", res, f"휴무: {holidays}", f"{visit_date.isoformat()}({WEEKDAY_NAMES[visit_date.weekday()]})", res == "fail"))

    # 4) 거리 (제약)
    dist = cand.get("distance_m")
    if conditions.constraint.max_walk_m is not None:
        limit = conditions.constraint.max_walk_m
        if dist is None:
            checks.append(Check("거리", "unknown", "좌표 미확인", "", True))
        else:
            checks.append(Check("거리", "pass" if dist <= limit else "fail", f"역에서 직선 {dist}m (한도 {limit}m)", "후보 Tool 직선거리", True))
    if conditions.constraint.max_walk_minutes is not None:
        limit = conditions.constraint.max_walk_minutes
        mins = estimate_walk_minutes(dist)
        if mins is None:
            checks.append(Check("도보시간", "unknown", "좌표 미확인", "", True))
        else:
            checks.append(Check("도보시간", "pass" if mins <= limit else "fail", f"도보 약 {mins}분 (한도 {limit}분)",
                                "직선거리×1.3÷67m/분 추정", True))

    # 5) 종료 시각 역산 (확인 가능한 값으로 기준 제시)
    if conditions.constraint.end_by is not None:
        need = cpolicy.meal_minutes + cpolicy.min_cafe_minutes + (estimate_walk_minutes(300) or 0)
        latest = (datetime.combine(visit_date, conditions.constraint.end_by) - timedelta(minutes=need)).time()
        res: Result = "unknown"
        if ref is not None:
            res = "pass" if ref <= latest else "fail"
        checks.append(Check("종료 시각", res, f"{conditions.constraint.end_by.strftime('%H:%M')}까지 끝내려면 늦어도 {latest.strftime('%H:%M')}에 식사 시작",
                            f"식사 {cpolicy.meal_minutes}분 + 카공 최소 {cpolicy.min_cafe_minutes}분 + 이동 추정 (정책 가정)", True))

    hard_problem = next((c for c in checks if c.hard and c.result in ("fail", "unknown")), None)
    excluded_reason = None
    if hard_problem:
        kind = "조건 불충족" if hard_problem.result == "fail" else "판단 불가"
        excluded_reason = f"{hard_problem.criterion} {kind}: {hard_problem.value}"

    # 점수 (제외 여부와 별개로 순위용)
    score = 100.0
    reasons: list[str] = []
    rainy = is_rainy(weather, wpolicy)
    if dist is not None:
        weight = 1.0
        if conditions.preference.prefer_short_walk:
            weight *= cpolicy.short_walk_weight
        if rainy:
            weight *= wpolicy.rain_distance_weight
        penalty = dist * cpolicy.distance_penalty_per_m * weight
        score -= penalty
        reasons.append(f"거리 {dist}m 감점 -{penalty:.1f}" + (" (비·도보 선호로 가중)" if weight > 1 else ""))
    if any(c.criterion == "영업시간" and c.result == "pass" for c in checks):
        score += 5
        reasons.append("영업시간 확인 +5")
    if menus:
        score += 3
        reasons.append("메뉴·가격 확인 +3")
    temp = (weather or {}).get("temperature_c")
    names = " ".join(m.get("name", "") for m in (matched or menus or []))
    if temp is not None and temp <= wpolicy.cold_temp_c and any(k in names for k in wpolicy.warm_keywords):
        score += wpolicy.warm_bonus
        reasons.append(f"기온 {temp}°C ≤ {wpolicy.cold_temp_c}°C, 따뜻한 메뉴(키워드) +{wpolicy.warm_bonus:g}")
    if temp is not None and temp >= wpolicy.hot_temp_c and any(k in names for k in wpolicy.cold_keywords):
        score += wpolicy.cold_bonus
        reasons.append(f"기온 {temp}°C ≥ {wpolicy.hot_temp_c}°C, 차가운 메뉴(키워드) +{wpolicy.cold_bonus:g}")
    if any(c.result == "unknown" and not c.hard for c in checks):
        score -= 5
        reasons.append("미확인 항목 -5")

    for c in checks:
        if c.result == "unknown" and not c.hard:
            warnings.append(c.value)

    return RestaurantEvaluation(
        key=cand_key(cand), name=cand["name"], source=cand["source"], source_id=cand["source_id"],
        status="excluded" if hard_problem else "satisfied", checks=checks, score=round(score, 1),
        score_reasons=reasons, excluded_reason=excluded_reason, matched_menus=matched[:5], warnings=warnings,
    )


@dataclass
class Evaluation:
    satisfied: list[RestaurantEvaluation]
    excluded: list[RestaurantEvaluation]
    criteria: list[str]
    weather_applied: list[str]
    hard_failure: dict[str, str] | None = None  # 재계획해도 같은 결과인 실패 (예: 키 누락)


NON_REPLANNABLE = {"MISSING_API_KEY", "INVALID_INPUT"}


def evaluate(data: ExecutionData, conditions: Conditions, today: date,
             wpolicy: WeatherPolicy = WEATHER_POLICY) -> Evaluation:
    visit = conditions.base.visit_date or today
    evaluated = []
    for cand in data.candidates[: data.detailed_count]:
        key = cand_key(cand)
        evaluated.append(evaluate_restaurant(cand, data.details.get(key), data.detail_errors.get(key), conditions,
                                             data.weather, visit, wpolicy))
    ranked = sorted((e for e in evaluated if e.status == "satisfied"), key=lambda e: -e.score)
    by_key = {cand_key(c): c for c in data.candidates}
    satisfied, seen_places = [], set()
    for e in ranked:
        c = by_key[e.key]
        place = (re.sub(r"\s|\(.*?\)", "", e.name), round(c.get("latitude") or 0, 4), round(c.get("longitude") or 0, 4))
        if place in seen_places:
            continue  # 원본에 같은 매장이 다른 ID 로 중복 등록된 경우 (ID 는 연결하지 않고 목록에서만 생략)
        seen_places.add(place)
        satisfied.append(e)
    excluded = [e for e in evaluated if e.status == "excluded"]

    criteria = []
    c = conditions
    if c.constraint.budget_max is not None:
        criteria.append(f"예산: {c.constraint.budget_max:,}원 이하 메뉴가 확인된 곳만 (가격 미확인은 제외)")
    ref, basis = reference_time(c)
    if ref:
        criteria.append(f"영업시간: {visit.isoformat()} {ref.strftime('%H:%M')} 영업 여부 ({basis}), 미확인은 경고 후 순위 하락")
    if c.constraint.max_walk_m:
        criteria.append(f"거리: 역에서 직선 {c.constraint.max_walk_m}m 이내")
    if c.constraint.max_walk_minutes:
        criteria.append(f"도보: 약 {c.constraint.max_walk_minutes}분 이내 (직선거리 기반 추정)")
    if c.preference.food_type:
        criteria.append(f"음식 종류: {c.preference.food_type}")
    if c.preference.exclude_food_types:
        criteria.append(f"제외 음식 종류: {', '.join(c.preference.exclude_food_types)}")

    applied = []
    w = data.weather
    if w:
        temp = w.get("temperature_c")
        if is_rainy(w, wpolicy):
            applied.append(f"강수확률 {w.get('precipitation_probability')}% / {w.get('precipitation_type')} → 가까운 식당·카페 우선, 카페 반경 축소")
        if temp is not None and temp <= wpolicy.cold_temp_c:
            applied.append(f"기온 {temp}°C → 따뜻한 메뉴 키워드 가산점")
        if temp is not None and temp >= wpolicy.hot_temp_c:
            applied.append(f"기온 {temp}°C → 차가운 메뉴 키워드 가산점")
        if not applied:
            applied.append("일반 날씨 → 취향·예산·거리 중심")
    else:
        applied.append("날씨 미확인 → 기본 정책(취향·예산·거리)")

    hard_failure = None
    if data.candidate_error and data.candidate_error.get("code") in NON_REPLANNABLE and not data.candidates:
        hard_failure = data.candidate_error
    return Evaluation(satisfied=satisfied, excluded=excluded, criteria=criteria, weather_applied=applied, hard_failure=hard_failure)


def cafe_radius(conditions: Conditions, weather: dict[str, Any] | None, cpolicy: CoursePolicy = COURSE_POLICY) -> int:
    if conditions.preference.prefer_short_walk or is_rainy(weather):
        return cpolicy.cafe_radius_short_walk_m
    return cpolicy.cafe_radius_m
