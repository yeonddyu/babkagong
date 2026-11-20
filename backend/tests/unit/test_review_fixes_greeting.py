"""Codex 2차 검증 결함 6: 확정적인 인사·도움말은 외부 호출(분석 LLM 포함) 0회."""
from __future__ import annotations

from app.agent.conditions import AnalysisResult, Conditions
from app.agent.graph import MainAgent
from tests.unit.agent_fixtures import TODAY, make_registry, make_session


class CountingLLM:
    def __init__(self):
        self.calls = 0

    def with_structured_output(self, _):
        return self

    def invoke(self, messages):
        self.calls += 1
        if isinstance(messages, list) and messages and messages[0][0] == "system" and "요청 분석기" in messages[0][1]:
            return AnalysisResult(intent="recommend", reason="LLM", decided_by="llm",
                                  conditions=Conditions.model_validate({"preference": {"area": "역삼역"}}))
        return type("Msg", (), {"content": ""})()


def _calls(registry):
    names = []
    original = registry.invoke

    def invoke(name, arguments=None):
        names.append(name)
        return original(name, arguments)

    registry.invoke = invoke
    return names


def test_greeting_and_help_make_no_external_calls(make_settings):
    registry = make_registry(make_settings, make_session())
    tools = _calls(registry)
    llm = CountingLLM()
    agent = MainAgent(registry, today_fn=lambda: TODAY, llm=llm)
    for msg, intent in (("안녕", "smalltalk"), ("도움말", "help"), ("고마워", "smalltalk"), ("사용법 알려줘", "help")):
        r = agent.run(msg)["response"]
        assert r["intent"] == intent and r["decided_by"] == "rule"
    assert llm.calls == 0 and tools == []


def test_greeting_mixed_with_recommendation_still_recommends(make_settings):
    llm = CountingLLM()
    agent = MainAgent(make_registry(make_settings, make_session()), today_fn=lambda: TODAY, llm=llm)
    r = agent.run("안녕, 역삼역 점심 추천해 줘")["response"]
    assert r["intent"] == "recommend" and r["conditions"]["preference"]["area"] == "역삼역"
    assert llm.calls >= 1  # 추천 요청은 분석 LLM 사용
