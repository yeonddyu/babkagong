"""Codex 2차 검증 결함 1: 명시한 역이 이전 대화·LLM·역 칩으로 바뀌는 문제."""
from __future__ import annotations

from app.agent.analysis import analyze
from app.agent.conditions import AnalysisResult, Conditions
from app.agent.graph import MainAgent
from tests.unit.agent_fixtures import TODAY, make_registry, make_session


def _capture(registry):
    calls = []
    original = registry.invoke

    def invoke(name, arguments=None):
        calls.append(name)
        return original(name, arguments)

    registry.invoke = invoke
    return calls


def test_unsupported_station_in_followup_clarifies_without_tools(make_settings):
    registry = make_registry(make_settings, make_session())
    agent = MainAgent(registry, today_fn=lambda: TODAY)
    first = agent.run("강남역 12시 점심 먹고 카공", area_hint="강남역")
    calls = _capture(registry)
    r = agent.run("같은 조건에서 홍대입구역에서 점심", session_id=first["session_id"], area_hint="역삼역")["response"]
    assert r["clarify"] is True and r["unsupported_area"] == "홍대입구역"
    assert "서비스 지역이 아니에요" in r["message"] and r["recommendations"] == []
    assert calls == []  # 추천 Tool 호출 0회


def test_supported_station_in_message_beats_chip_and_history(make_settings):
    agent = MainAgent(make_registry(make_settings, make_session()), today_fn=lambda: TODAY)
    first = agent.run("강남역 12시 점심 먹고 카공", area_hint="강남역")
    named = agent.run("같은 조건에서 선릉역에서 점심", session_id=first["session_id"], area_hint="역삼역")
    assert named["response"]["conditions"]["preference"]["area"] == "선릉역"
    plain = agent.run("같은 조건으로 다시 추천해줘", session_id=first["session_id"], area_hint="언주역")
    assert plain["response"]["conditions"]["preference"]["area"] == "언주역"  # 역 언급 없음 → 역 칩 우선


class FakeLLM:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def with_structured_output(self, schema):
        return self

    def invoke(self, _messages):
        self.calls += 1
        return self.result


def test_llm_cannot_replace_station_named_in_message():
    fake = AnalysisResult(intent="recommend", reason="LLM", decided_by="llm",
                          conditions=Conditions.model_validate({"preference": {"area": "선릉역"}}))
    r = analyze("선정릉역 선릉 쪽과 무관한 점심", TODAY, FakeLLM(fake))
    assert r.decided_by == "llm" and r.conditions.preference.area == "선정릉역"


def test_llm_area_used_only_when_rules_found_none_and_name_in_message():
    fake = AnalysisResult(intent="recommend", reason="LLM", decided_by="llm",
                          conditions=Conditions.model_validate({"preference": {"area": "신논현역"}}))
    assert analyze("신논현 점심 추천", TODAY, FakeLLM(fake)).conditions.preference.area == "신논현역"  # 규칙은 못 찾음
    assert analyze("점심 추천해줘", TODAY, FakeLLM(fake)).conditions.preference.area is None  # 발화에 없는 역
