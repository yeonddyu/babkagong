"""F3013 실행 로그 저장 - 단위 테스트 (SQLite 메모리 DB)."""
from __future__ import annotations

import pytest

from app.agent.graph import MainAgent
from app.events.bus import EventBus
from app.events.logging_agent import LoggingAgent
from app.storage.db import init_db, make_engine, make_session_factory
from app.storage.logs import LogRepository
from tests.unit.agent_fixtures import TODAY, make_registry, make_session


@pytest.fixture
def repo():
    engine = make_engine("sqlite://")
    init_db(engine)
    return LogRepository(make_session_factory(engine))


def make_agent(make_settings, bus):
    return MainAgent(make_registry(make_settings, make_session()), today_fn=lambda: TODAY, bus=bus)


def test_logging_agent_saves_events_per_session_in_order(make_settings, repo):
    bus = EventBus()
    LoggingAgent(repo).attach(bus)
    agent = make_agent(make_settings, bus)
    r1 = agent.run("강남역 점심 추천", session_id="A")
    agent.run("안녕", session_id="B")
    a_logs = repo.get_session("A")
    assert [(l["seq"], l["type"]) for l in a_logs] == [(e["seq"], e["type"]) for e in r1["events"]]
    assert all(l["session_id"] == "A" for l in a_logs)
    assert all(l["session_id"] == "B" for l in repo.get_session("B"))  # 세션 섞이지 않음
    # 발생한 사실을 그대로 저장 (원본 payload 동일)
    assert a_logs[0]["payload"] == r1["events"][0]["payload"]


def test_logging_agent_does_not_use_llm(make_settings, repo):
    class ExplodingLLM:
        def __getattr__(self, name):
            raise AssertionError("로깅 Agent 가 LLM 을 호출함")

    bus = EventBus()
    la = LoggingAgent(repo).attach(bus)
    assert la.uses_llm is False and not hasattr(la, "llm")
    make_agent(make_settings, bus).run("강남역 점심 추천", session_id="x")
    assert la.saved == len(repo.get_session("x")) > 0


def test_storage_failure_does_not_break_conversation(make_settings):
    class BrokenSink:
        def append(self, event):
            raise OSError("disk full")

    bus = EventBus()
    la = LoggingAgent(BrokenSink()).attach(bus)
    r = make_agent(make_settings, bus).run("강남역 점심 추천")
    assert r["response"]["recommendations"] and la.failed > 0 and la.saved == 0


def test_agent_runs_without_logging_agent(make_settings, repo):
    r = make_agent(make_settings, EventBus()).run("강남역 점심 추천", session_id="none")
    assert r["response"]["recommendations"] and repo.get_session("none") == []


def test_detach(make_settings, repo):
    bus = EventBus()
    la = LoggingAgent(repo).attach(bus)
    la.detach()
    make_agent(make_settings, bus).run("안녕", session_id="d")
    assert repo.get_session("d") == []
