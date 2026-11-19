"""F3008 제약 적합성 판단 - 단위 테스트."""
from __future__ import annotations

from datetime import date, time

import pytest

from app.agent.analysis import rule_analyze
from app.agent.graph import MainAgent
from app.agent.judge import closed_on, evaluate_restaurant, open_at
from tests.unit.agent_fixtures import TODAY, kma_handler, make_registry, make_session

THU = TODAY  # 2026-11-19 목요일
SUN = date(2026, 11, 22)


@pytest.mark.parametrize("text, wd, at, expected", [
    ("매일 11:00~21:00", 3, time(12), "pass"),
    ("매일 11:00~21:00", 3, time(22), "fail"),
    ("매일 11:30~15:00, 매일 17:30~21:30", 3, time(16), "fail"),
    ("평일 11:30~22:00, 주말 12:00~21:00", 5, time(11, 45), "fail"),
    ("평일 17:00~07:00", 3, time(2), "pass"),  # 자정 넘김
    ("평일 11:30~22:00", 6, time(12), "unknown"),  # 일요일 정보 없음 → 추정하지 않음
    ("월~금 09:00~18:00", 4, time(12), "pass"),
    ("전화 문의", 3, time(12), "unknown"),
])
def test_open_at(text, wd, at, expected):
    assert open_at(text, wd, at)[0] == expected


@pytest.mark.parametrize("text, day, expected", [
    ("일요일", SUN, "fail"), ("일요일", THU, "pass"), ("연중무휴", SUN, "pass"), ("주말, 공휴일", SUN, "fail"),
])
def test_closed_on(text, day, expected):
    assert closed_on(text, day) == expected


def cond(msg):
    return rule_analyze(msg, TODAY).conditions


CAND = {"name": "테스트", "source": "seoul_tourism_redtable", "source_id": "1", "distance_m": 100}


def detail(menus=None, hours=None, holidays=None, available=True):
    return {"detail_available": available, "menus": menus, "operation": {"business_hours": hours, "holidays": holidays} if hours or holidays else None}


def test_budget_pass_fail_unknown():
    c = cond("강남역 1만원 이하 점심")
    ok = evaluate_restaurant(CAND, detail([{"name": "김치찌개", "price_krw": 9000}, {"name": "제육", "price_krw": 11000}]), None, c, None, THU)
    assert ok.status == "satisfied" and [m["name"] for m in ok.matched_menus] == ["김치찌개"]
    over = evaluate_restaurant(CAND, detail([{"name": "초밥", "price_krw": 22000}]), None, c, None, THU)
    assert over.status == "excluded" and "최저가 22,000원 > 예산 10,000원" in over.excluded_reason
    unknown = evaluate_restaurant(CAND, detail([]), None, c, None, THU)
    assert unknown.status == "excluded" and "판단 불가" in unknown.excluded_reason
    assert "매장에서 확인" in unknown.excluded_reason  # 역산 기준 제시, 가격 추정 안 함
    partial = evaluate_restaurant(CAND, detail([{"name": "A", "price_krw": None}, {"name": "B", "price_krw": 20000}]), None, c, None, THU)
    assert partial.status == "excluded" and "판단 불가" in partial.excluded_reason  # 가격 없는 메뉴를 예산 이하로 가정하지 않음


def test_hours_fail_excludes_unknown_warns():
    c = cond("강남역 12시 점심")
    closed = evaluate_restaurant(CAND, detail([], "매일 17:00~23:00"), None, c, None, THU)
    assert closed.status == "excluded" and "영업시간" in closed.excluded_reason
    no_info = evaluate_restaurant(CAND, detail([]), None, c, None, THU)
    assert no_info.status == "satisfied" and any("영업시간 미확인" in w for w in no_info.warnings)
    assert "미확인 항목 -5" in no_info.score_reasons


def test_period_reference_time_is_labelled_assumption():
    e = evaluate_restaurant(CAND, detail([], "매일 11:00~21:00"), None, cond("강남역 점심"), None, THU)
    hours = next(ch for ch in e.checks if ch.criterion == "영업시간")
    assert hours.result == "pass" and "가정" in hours.basis


def test_holiday_and_distance_constraints():
    e = evaluate_restaurant(CAND, detail([], "매일 08:00~20:00", "일요일"), None, cond("일요일 강남역 점심"), None, SUN)
    assert e.status == "excluded" and "휴무일" in e.excluded_reason
    far = dict(CAND, distance_m=450)
    e2 = evaluate_restaurant(far, detail([]), None, cond("강남역 300m 이내 점심"), None, THU)
    assert e2.status == "excluded" and "450m" in e2.excluded_reason
    e3 = evaluate_restaurant(far, detail([]), None, cond("강남역 도보 5분 이내 점심"), None, THU)
    assert e3.status == "excluded" and "도보" in e3.excluded_reason  # 450*1.3/67 → 9분


def test_end_by_reverse_calculation():
    e = evaluate_restaurant(CAND, detail([]), None, cond("강남역 1시 점심 먹고 3시까지 카공"), None, THU)
    end = next(ch for ch in e.checks if ch.criterion == "종료 시각")
    assert "늦어도" in end.value and end.result == "fail"  # 13:00 시작 > 역산 기준
    assert e.status == "excluded"


def test_license_candidate_without_details_with_budget_excluded():
    lic = dict(CAND, source="gangnam_general_restaurant_license")
    d = {"detail_available": False, "menus": None, "operation": None, "detail_unavailable": {"message": "메뉴 미제공"}}
    e = evaluate_restaurant(lic, d, None, cond("강남역 1만원 이하"), None, THU)
    assert e.status == "excluded" and e.matched_menus == []


def test_weather_scoring():
    c = cond("강남역 점심")
    warm = detail([{"name": "김치찌개", "price_krw": 9000}])
    neutral = detail([{"name": "샐러드", "price_krw": 9000}])
    cold_w = {"temperature_c": 2.0, "precipitation_probability": 0, "precipitation_type": "없음"}
    a = evaluate_restaurant(CAND, warm, None, c, cold_w, THU)
    b = evaluate_restaurant(CAND, neutral, None, c, cold_w, THU)
    assert a.score - b.score == 10 and any("따뜻한 메뉴" in r for r in a.score_reasons)
    hot_w = {"temperature_c": 30.0, "precipitation_probability": 0, "precipitation_type": "없음"}
    noodle = evaluate_restaurant(CAND, detail([{"name": "물냉면", "price_krw": 11000}]), None, c, hot_w, THU)
    assert any("차가운 메뉴" in r for r in noodle.score_reasons)
    rain = {"temperature_c": 12.0, "precipitation_probability": 80, "precipitation_type": "비"}
    near = evaluate_restaurant(dict(CAND, distance_m=100), neutral, None, c, rain, THU)
    far = evaluate_restaurant(dict(CAND, distance_m=500), neutral, None, c, rain, THU)
    dry_far = evaluate_restaurant(dict(CAND, distance_m=500), neutral, None, c, None, THU)
    assert near.score > far.score and far.score < dry_far.score  # 비 오면 거리 감점 가중


def test_weather_does_not_override_user_preference(make_settings):
    session = make_session(kma=kma_handler(tmp="1"))
    agent = MainAgent(make_registry(make_settings, session), today_fn=lambda: TODAY)
    result = agent.run("강남역 일식 점심 추천")
    names = [e.name for e in result["evaluation"].satisfied]
    assert names and all(n in ("스시하우스", "라멘가게") for n in names)  # 추워도 한식으로 바꾸지 않음


def test_agent_judge_with_budget(make_settings):
    agent = MainAgent(make_registry(make_settings, make_session()), today_fn=lambda: TODAY)
    result = agent.run("강남역에서 1만원 이하로 12시 점심")
    ev = result["evaluation"]
    assert [e.name for e in ev.satisfied] == ["김치찌개집", "일요일휴무 백반", "칼국수집"]
    reasons = {e.name: e.excluded_reason for e in ev.excluded}
    assert "최저가" in reasons["스시하우스"] and "판단 불가" in reasons["가격미상 국밥"]
    assert any("예산" in c for c in ev.criteria)
    # 카페는 충족한 식당만 찾음
    cafe_targets = {(c["args"]["latitude"]) for c in result["tool_calls"] if c["tool"] == "search_nearby_cafes"}
    assert len(cafe_targets) == 3


@pytest.mark.parametrize("text, wd, at, expected", [
    ("평일 10:30~22:00, 공휴일 11:00~20:30", 6, time(12), "unknown"),  # 공휴일 구간을 매일로 해석하지 않음
    ("매일 11:00~22:00, 브레이크타임 15:00~17:00", 3, time(16), "fail"),
    ("매일 11:00~22:00, 브레이크타임 15:00~17:00", 3, time(12), "pass"),
])
def test_open_at_holiday_and_break_segments(text, wd, at, expected):
    assert open_at(text, wd, at)[0] == expected


def test_closed_on_other_weekday_passes():
    assert closed_on("일요일", THU) == "pass" and closed_on("일요일, 공휴일", THU) == "pass"
    assert closed_on("공휴일", THU) == "unknown"


def test_side_dishes_do_not_satisfy_budget():
    c = cond("강남역 1만원 이하 점심")
    d = detail([{"name": "공기밥", "price_krw": 1000}, {"name": "곱빼기 추가", "price_krw": 1500},
                {"name": "연유라떼", "price_krw": 1}, {"name": "짬뽕", "price_krw": 11000}])
    e = evaluate_restaurant(CAND, d, None, c, None, THU)
    assert e.status == "excluded" and "최저가 11,000원" in e.excluded_reason
    d2 = detail([{"name": "공기밥", "price_krw": 1000}, {"name": "짜장면", "price_krw": 8000}])
    assert [m["name"] for m in evaluate_restaurant(CAND, d2, None, c, None, THU).matched_menus] == ["짜장면"]


def test_same_place_registered_twice_recommended_once(make_settings):
    from tests.unit.agent_fixtures import GANGNAM, MENUS, OPRT_ROWS, YEOKSAM, make_session as ms
    from tests.unit.test_f3002_restaurant_candidates import rt_row as rr

    rows = [GANGNAM[0], rr(99, "김치찌개집", 37.4981, 127.0277)] + GANGNAM[1:] + YEOKSAM
    menus = [{"MENU_ID": i, "MENU_NM": n, "MENU_PRICE": p, "RSTR_ID": r} for i, (r, n, p) in enumerate(MENUS + [(99, "김치찌개", 9000)], 1)]
    agent = MainAgent(make_registry(make_settings, ms(rt_rows=rows, menus=menus)), today_fn=lambda: TODAY)
    names = [e.name for e in agent.run("강남역 1만원 이하 12시 점심")["evaluation"].satisfied]
    assert names.count("김치찌개집") == 1


def test_liquor_not_meal_and_matched_sorted_near_budget():
    c = cond("강남역 1만 5천원 이하 점심")
    d = detail([{"name": "이과두주", "price_krw": 5000}, {"name": "짬뽕", "price_krw": 9000}, {"name": "탕수육(소)", "price_krw": 14000},
                {"name": "짜장면", "price_krw": 7000}])
    e = evaluate_restaurant(CAND, d, None, c, None, THU)
    assert [m["name"] for m in e.matched_menus] == ["탕수육(소)", "짬뽕", "짜장면"]


def test_drink_only_shop_is_not_a_meal_place():
    """실제 데이터: 버블티 가게가 점심 식당으로 추천된 문제 재현."""
    d = detail([{"name": "딸기스무디", "price_krw": 4500}, {"name": "타로버블티", "price_krw": 4000},
                {"name": "아메리카노(HOT)", "price_krw": 2500}])
    e = evaluate_restaurant(CAND, d, None, cond("강남역 점심"), None, THU)
    assert e.status == "excluded" and "식사 메뉴" in e.excluded_reason
    e2 = evaluate_restaurant(CAND, d, None, cond("강남역 1만 2천원 이하 점심"), None, THU)
    assert e2.status == "excluded"


def test_coffee_names_and_one_won_items_not_meals():
    d = detail([{"name": "카페모카", "price_krw": 3000}, {"name": "카라멜마끼아또", "price_krw": 3000},
                {"name": "베이비슈", "price_krw": 1}, {"name": "밀크티버블티", "price_krw": 4000}])
    assert evaluate_restaurant(CAND, d, None, cond("강남역 점심"), None, THU).status == "excluded"
    ok = detail([{"name": "쌀국수", "price_krw": 9000}, {"name": "아메리카노", "price_krw": 2000}])
    assert evaluate_restaurant(CAND, ok, None, cond("강남역 점심"), None, THU).status == "satisfied"


def test_meal_names_ending_like_drinks_are_meals():
    from app.agent.judge import is_meal_menu

    for name in ("까르보나라 스파게티", "토마토 스파게티", "로제 파스타", "돈코츠라멘"):
        assert is_meal_menu({"name": name, "price_krw": 12000}), name
    for name in ("복숭아 아이스티", "카페모카", "초코라떼"):
        assert not is_meal_menu({"name": name, "price_krw": 4000}), name


def test_sauce_in_dish_name_is_meal():
    from app.agent.judge import is_meal_menu

    assert is_meal_menu({"name": "깐소중새우(칠리소스/small)", "price_krw": 18000})
    assert not is_meal_menu({"name": "소스 추가", "price_krw": 3000})
