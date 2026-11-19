"""추천 5곳 표시와 '더 보기'(같은 조건으로 다음 후보) - 단위 테스트 (Mock 외부 API)."""
from __future__ import annotations

import pytest

from app.agent.analysis import rule_analyze
from app.agent.graph import MainAgent
from app.agent.memory import InMemoryMemoryStore
from tests.unit.agent_fixtures import TODAY, make_registry, make_session
from tests.unit.test_f3002_restaurant_candidates import rt_row

# 강남역 앞 14곳, 모두 메뉴(8천원)와 영업시간이 확인된 식당
ROWS = [rt_row(400 + i, f"식당{i:02d}", 37.4980 + i * 0.00003, 127.0277) for i in range(14)]
MENUS = [{"MENU_ID": i, "MENU_NM": "백반", "MENU_PRICE": 8000, "RSTR_ID": 400 + i} for i in range(14)]


def agent(make_settings, store=None):
    return MainAgent(make_registry(make_settings, make_session(rt_rows=ROWS, menus=MENUS)),
                     today_fn=lambda: TODAY, memory=store or InMemoryMemoryStore())


@pytest.mark.parametrize("msg", ["다른 곳 더 보여줘", "더 추천해줘", "다른 식당도 더 알려줘", "추가로 추천해줘"])
def test_more_intent(msg):
    r = rule_analyze(msg, TODAY)
    assert r.intent == "recommend" and r.more and r.is_followup


def test_not_more():
    assert rule_analyze("강남역 점심 추천", TODAY).more is False


def test_shows_up_to_five(make_settings):
    body = agent(make_settings).run("강남역 1만원 이하 점심", session_id="s")["response"]
    assert len(body["recommendations"]) == 5
    assert all(r["cafes"] for r in body["recommendations"])  # 5곳 모두 주변 카페 검색


def test_more_returns_new_places_with_same_conditions(make_settings):
    a = agent(make_settings)
    first = a.run("강남역 1만원 이하 점심", session_id="s")
    second = a.run("다른 곳 더 보여줘", session_id="s")
    names1 = [r["name"] for r in first["response"]["recommendations"]]
    names2 = [r["name"] for r in second["response"]["recommendations"]]
    assert len(names2) == 5 and not set(names1) & set(names2)  # 이미 보여 준 곳은 다시 추천하지 않음
    assert second["conditions"].constraint.budget_max == 10000 and second["conditions"].preference.area == "강남역"
    assert second["response"]["more"] is True
    assert any("앞서 보여 드린 5곳은 제외" in c for c in second["response"]["criteria"])
    third = a.run("더 보여줘", session_id="s")
    names3 = [r["name"] for r in third["response"]["recommendations"]]
    assert names3 and not (set(names3) & (set(names1) | set(names2)))  # 누적 제외


def test_more_skips_same_name_registered_twice(make_settings):
    """실제 데이터: 같은 가게(앤디캔디솜사탕)가 다른 ID·좌표로 두 번 등록되어 '더 보기'에 다시 나온 문제."""
    rows = ROWS[:5] + [rt_row(499, "식당00(본점)", 37.4995, 127.0300)] + ROWS[5:]
    menus = MENUS + [{"MENU_ID": 99, "MENU_NM": "백반", "MENU_PRICE": 8000, "RSTR_ID": 499}]
    a = MainAgent(make_registry(make_settings, make_session(rt_rows=rows, menus=menus)), today_fn=lambda: TODAY,
                  memory=InMemoryMemoryStore())
    first = [r["name"] for r in a.run("강남역 1만원 이하 점심", session_id="d")["response"]["recommendations"]]
    assert "식당00" in first
    second = [r["name"] for r in a.run("더 보여줘", session_id="d")["response"]["recommendations"]]
    assert "식당00(본점)" not in second


def test_new_request_resets_shown(make_settings):
    store = InMemoryMemoryStore()
    a = agent(make_settings, store)
    a.run("강남역 1만원 이하 점심", session_id="s")
    a.run("더 보여줘", session_id="s")
    assert len(store.load("s")["shown"]) == 10 and len(store.load("s")["shown_names"]) == 10
    a.run("강남역 점심 추천해줘", session_id="s")
    assert len(store.load("s")["shown"]) == 5


def test_more_without_previous_is_normal_request(make_settings):
    r = agent(make_settings).run("더 보여줘", session_id="new", area_hint="강남역")
    assert r["response"]["more"] is False and r["response"]["recommendations"]
