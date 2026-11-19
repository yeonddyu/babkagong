"""F3014 실행 로그 조회 및 삭제 - 단위 테스트."""
from __future__ import annotations

import pytest

from app.agent.graph import MainAgent
from app.events.bus import EventBus
from app.events.logging_agent import LoggingAgent
from app.storage.db import init_db, make_engine, make_session_factory
from app.storage.logs import LogRepository
from tests.unit.agent_fixtures import TODAY, make_registry, make_session


@pytest.fixture
def setup(make_settings):
    engine = make_engine("sqlite://")
    init_db(engine)
    repo = LogRepository(make_session_factory(engine))
    bus = EventBus()
    LoggingAgent(repo).attach(bus)
    agent = MainAgent(make_registry(make_settings, make_session()), today_fn=lambda: TODAY, bus=bus)
    return repo, agent


def test_list_sessions(setup):
    repo, agent = setup
    agent.run("강남역 점심 추천", session_id="s1")
    agent.run("같은 조건에서 일식으로", session_id="s1")
    agent.run("안녕", session_id="s2")
    sessions = {s["session_id"]: s for s in repo.list_sessions()}
    assert set(sessions) == {"s1", "s2"}
    assert sessions["s1"]["run_count"] == 2 and sessions["s2"]["run_count"] == 1
    assert sessions["s1"]["first_message"] == "강남역 점심 추천"
    assert sessions["s1"]["event_count"] == len(repo.get_session("s1"))


def test_detail_in_execution_order(setup):
    repo, agent = setup
    r1 = agent.run("강남역 점심 추천", session_id="s")
    r2 = agent.run("안녕", session_id="s")
    logs = repo.get_session("s")
    assert [l["run_id"] for l in logs] == [r1["run_id"]] * len(r1["events"]) + [r2["run_id"]] * len(r2["events"])
    assert [l["seq"] for l in logs if l["run_id"] == r1["run_id"]] == list(range(1, len(r1["events"]) + 1))
    assert logs[0]["type"] == "run_start" and logs[len(r1["events"]) - 1]["type"] == "run_end"


def test_delete_session(setup):
    repo, agent = setup
    agent.run("안녕", session_id="del")
    agent.run("안녕", session_id="keep")
    assert repo.delete_session("del") > 0
    assert repo.get_session("del") == [] and repo.get_session("keep")
    assert repo.delete_session("del") == 0


def test_no_update_capability():
    public = {name for name in dir(LogRepository) if not name.startswith("_")}
    assert public == {"append", "list_sessions", "get_session", "delete_session"}
    assert not any(w in name for name in public for w in ("update", "edit", "modify", "set"))
