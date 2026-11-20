"""Codex 2차 검증 결함 5: 한 자리 거리 제약 유지 (+ 도보 분 환산·가까운 순 회귀)."""
from __future__ import annotations

from app.agent.analysis import analyze, parse_walk
from app.agent.conditions import AnalysisResult, Conditions
from app.agent.graph import MainAgent
from tests.unit.agent_fixtures import TODAY, make_registry, make_session
from tests.unit.test_candidate_variety import _capture


def test_parse_single_digit_metres():
    assert parse_walk("역삼역 9m 이내 점심") == (9, None)
    assert parse_walk("300미터 안") == (300, None)
    assert parse_walk("1.5m") == (None, None)  # 소수 일부를 잘라 읽지 않음
    assert parse_walk("도보 3분 이내") == (None, 3)


def test_rule_metres_beat_llm():
    class Fake:
        def with_structured_output(self, _):
            return self

        def invoke(self, _):
            return AnalysisResult(intent="recommend", reason="", decided_by="llm",
                                  conditions=Conditions.model_validate({"preference": {"area": "역삼역"}}))
    assert analyze("역삼역 9m 이내 점심", TODAY, Fake()).conditions.constraint.max_walk_m == 9


def test_nine_metre_limit_applied_in_final_check(make_settings):
    registry = make_registry(make_settings, make_session())
    calls = _capture(registry)
    r = MainAgent(registry, today_fn=lambda: TODAY, seed_fn=lambda: 1).run("강남역 9m 이내 12시 점심")["response"]
    assert r["conditions"]["constraint"]["max_walk_m"] == 9
    assert calls[0]["radius_m"] == 50  # 후보 Tool 최소 반경은 50m 유지
    assert all(x["distance_m"] <= 9 for x in r["recommendations"])
    assert "거리: 강남역에서 직선 9m 이내" in r["criteria"]
    assert any("거리" in x["reason"] and "조건 불충족" in x["reason"] for x in r["excluded"])  # 9m 넘는 후보는 제외


def test_walk_minutes_and_short_walk_regressions(make_settings):
    registry = make_registry(make_settings, make_session())
    calls = _capture(registry)
    agent = MainAgent(registry, today_fn=lambda: TODAY, seed_fn=lambda: 1)
    agent.run("강남역에서 도보 3분 이내로 점심")
    agent.run("강남역 점심, 많이 걷기는 싫어", session_id="s2")
    assert calls[0]["radius_m"] == 154 and calls[0]["order"] == "varied"
    assert calls[1]["order"] == "distance" and "radius_m" not in calls[1]
