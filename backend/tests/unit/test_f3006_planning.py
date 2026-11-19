"""F3006 작업 계획 수립 - 단위 테스트."""
from __future__ import annotations

from datetime import date

import pytest

from app.agent.analysis import rule_analyze
from app.agent.planning import build_plan

TODAY = date(2026, 11, 19)


def plan_for(msg):
    a = rule_analyze(msg, TODAY)
    return build_plan(a, a.conditions, TODAY)


def test_recommend_plan_order_and_inputs():
    p = plan_for("강남역에서 점심 먹고 카공할 건데 추천해줘")
    assert p.mode == "tools"
    assert [s.tool for s in p.steps] == ["get_weather_context", "search_restaurant_candidates", "get_restaurant_details", "search_nearby_cafes"]
    assert [s.order for s in p.steps] == [1, 2, 3, 4]
    assert "source_id" in p.steps[2].inputs_from and "latitude" in p.steps[3].inputs_from


@pytest.mark.parametrize("msg", ["안녕", "사용법 알려줘", "이 코스로 저장해줘", "오늘 주식 어때?"])
def test_no_tool_requests_skip_plan(msg):
    p = plan_for(msg)
    assert p.mode == "skip" and p.steps == []


def test_same_topic_with_and_without_tools_differ():
    assert plan_for("강남역 점심 추천").steps != plan_for("안녕 반가워").steps


def test_missing_area_asks_before_tools():
    p = plan_for("점심 먹고 카공할 곳 추천해줘")
    assert p.mode == "clarify" and p.missing == ["area"] and p.steps == []


def test_weather_excluded_out_of_range():
    p = plan_for("12월 25일 강남역 점심 추천")
    assert "get_weather_context" not in [s.tool for s in p.steps]
    assert p.excluded_tools[0]["tool"] == "get_weather_context"
