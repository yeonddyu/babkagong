"""F3010 대화 맥락 유지 - 단위 테스트 (Mock 외부 API)."""
from __future__ import annotations

import json
from datetime import date, time

from app.agent.graph import MainAgent
from app.agent.memory import InMemoryMemoryStore
from tests.unit.agent_fixtures import TODAY, make_registry, make_session


def agent(make_settings, memory=None):
    return MainAgent(make_registry(make_settings, make_session()), today_fn=lambda: TODAY, memory=memory or InMemoryMemoryStore())


def test_followup_changes_only_mentioned_field(make_settings):
    a = agent(make_settings)
    first = a.run("내일 12시 강남역에서 2만원 이하 한식 점심 추천해줘", session_id="s1")
    second = a.run("같은 조건에서 한식 말고 일식으로 바꿔줘", session_id="s1")
    c1, c2 = first["conditions"], second["conditions"]
    assert second["used_previous"] is True
    assert c2.preference.food_type == "일식" and c2.preference.exclude_food_types == ["한식"]
    # 바뀌지 않은 조건은 유지
    assert c2.base.visit_date == c1.base.visit_date == date(2026, 11, 20)
    assert c2.base.meal_time == time(12, 0) and c2.constraint.budget_max == 20000 and c2.preference.area == "강남역"
    assert set(second["changed_fields"]) == {"preference.food_type", "preference.exclude_food_types"}
    # 일식 후보만 다시 구성 (후보 Tool 을 food_type=일식 으로 다시 호출)
    cand_args = [c["args"] for c in second["tool_calls"] if c["tool"] == "search_restaurant_candidates"]
    assert cand_args[0]["food_type"] == "일식" and cand_args[0]["area"] == "강남역"


def test_sessions_are_isolated(make_settings):
    a = agent(make_settings)
    a.run("강남역 1만원 이하 점심", session_id="A")
    other = a.run("점심 추천해줘", session_id="B")
    assert other["used_previous"] is False and other["plan"].mode == "clarify"


def test_reset_drops_previous(make_settings):
    a = agent(make_settings)
    a.run("강남역 1만원 이하 한식 점심", session_id="s")
    r = a.run("처음부터 새로 추천, 역삼역 저녁", session_id="s")
    assert r["used_previous"] is False and r["conditions"].constraint.budget_max is None


def test_new_full_request_without_followup_is_fresh(make_settings):
    a = agent(make_settings)
    a.run("강남역 1만원 이하 한식 점심", session_id="s")
    r = a.run("역삼역 저녁 추천해줘", session_id="s")
    assert r["used_previous"] is False and r["conditions"].preference.food_type is None


def test_memory_keeps_summary_not_raw_responses(make_settings):
    store = InMemoryMemoryStore()
    a = agent(make_settings, store)
    a.run("강남역 1만원 이하 12시 점심 추천", session_id="m")
    mem = store.load("m")
    assert set(mem) == {"conditions", "last_intent", "recommendations", "shown", "shown_names"}
    assert all(":" in k for k in mem["shown"])  # 출처:식별자만 보관
    rec = mem["recommendations"][0]
    assert set(rec) == {"restaurant", "menus", "business_hours", "cafes"}
    raw = json.dumps(mem, ensure_ascii=False)
    for forbidden in ("source_status", "query_basis", "menu_status", "operation_status", "not_provided_fields", "RSTR_"):
        assert forbidden not in raw


def test_smalltalk_keeps_previous_context(make_settings):
    store = InMemoryMemoryStore()
    a = agent(make_settings, store)
    a.run("강남역 1만원 이하 점심", session_id="k")
    before = store.load("k")
    a.run("고마워!", session_id="k")
    assert store.load("k") == before


def test_memory_store_failure_does_not_break_agent(make_settings):
    class Broken:
        def load(self, sid):
            raise RuntimeError("db down")

        def save(self, sid, m):
            raise RuntimeError("db down")

    r = agent(make_settings, Broken()).run("강남역 점심 추천", session_id="x")
    assert r["evaluation"].satisfied
