"""F3015 계획 저장 및 조회 - 단위 테스트."""
from __future__ import annotations

from datetime import date, time

import pytest
from pydantic import ValidationError

from app.agent.graph import MainAgent
from app.agent.memory import InMemoryMemoryStore
from app.storage.db import init_db, make_engine, make_session_factory
from app.storage.plans import PlanCreate, PlanNotFound, PlanRepository
from tests.unit.agent_fixtures import TODAY, make_registry, make_session


@pytest.fixture
def repo():
    engine = make_engine("sqlite://")
    init_db(engine)
    return PlanRepository(make_session_factory(engine))


def plan(title="점심+카공", d=date(2026, 11, 20), s=time(12), e=time(15), **kw):
    return PlanCreate(title=title, plan_date=d, start_time=s, end_time=e, restaurant_name="김치찌개집", **kw)


def test_save_list_detail_with_created_at(repo):
    p, conflicts = repo.create(plan(area="강남역", cafe_name="카페1", restaurant_source="seoul_tourism_redtable",
                                    restaurant_source_id="1"))
    assert conflicts == [] and p.id and p.created_at
    listed = repo.list()
    assert [x.id for x in listed] == [p.id] and listed[0].restaurant_name == "김치찌개집"
    got = repo.get(p.id)
    assert got.plan_date == date(2026, 11, 20) and got.start_time == time(12) and got.cafe_name == "카페1"
    assert repo.list(date(2026, 11, 21)) == []


def test_overlap_saved_but_reported(repo):
    first, _ = repo.create(plan("A", s=time(12), e=time(15)))
    repo.create(plan("다른 날", d=date(2026, 11, 21), s=time(12), e=time(15)))
    touching, c0 = repo.create(plan("B", s=time(15), e=time(16)))  # 맞닿음은 겹침 아님
    assert c0 == []
    second, conflicts = repo.create(plan("C", s=time(14), e=time(17)))
    assert second.id and [c.id for c in conflicts] == [first.id, touching.id]
    assert len(repo.list()) == 4  # 저장은 막지 않음


def test_validation():
    with pytest.raises(ValidationError):
        plan(s=time(15), e=time(12))
    with pytest.raises(ValidationError):
        PlanCreate(title="", plan_date=date(2026, 11, 20), start_time=time(1), end_time=time(2), restaurant_name="x")


def test_not_found(repo):
    with pytest.raises(PlanNotFound):
        repo.get(999)


def test_save_recommended_course_via_conversation(make_settings, repo):
    agent = MainAgent(make_registry(make_settings, make_session()), today_fn=lambda: TODAY,
                      memory=InMemoryMemoryStore(), plan_repo=repo)
    agent.run("내일 12시 강남역 1만원 이하 점심 먹고 카공", session_id="s")
    r = agent.run("이 코스로 저장해줘", session_id="s")
    body = r["response"]
    saved = body["saved_plan"]
    assert saved["restaurant_name"] == "김치찌개집" and saved["restaurant_source_id"] == "1"
    assert saved["plan_date"] == "2026-11-20" and saved["start_time"] == "12:00:00" and saved["end_time"] == "15:00:00"
    assert saved["cafe_name"] and saved["created_at"]
    assert r["tool_calls"] == []  # 저장은 Tool 호출 없이 실행 흐름이 직접 처리
    assert "계획을 저장했어요" in body["message"]
    # 같은 시간대에 또 저장 → 저장되고 충돌 안내
    r2 = agent.run("2번 코스도 저장해줘", session_id="s")
    assert r2["response"]["saved_plan"]["id"] != saved["id"]
    assert [c["id"] for c in r2["response"]["plan_conflicts"]] == [saved["id"]]
    assert "겹치는 계획" in r2["response"]["message"]
    assert any(e["type"] == "stage_start" and e["stage"] == "save" for e in r2["events"])


def test_save_without_previous_recommendation(make_settings, repo):
    agent = MainAgent(make_registry(make_settings, make_session()), today_fn=lambda: TODAY, plan_repo=repo)
    body = agent.run("이 코스로 저장해줘", session_id="new")["response"]
    assert body["saved_plan"] is None and "먼저 추천" in body["message"] and repo.list() == []


def test_save_assumptions_when_time_missing(make_settings, repo):
    agent = MainAgent(make_registry(make_settings, make_session()), today_fn=lambda: TODAY, plan_repo=repo)
    agent.run("강남역 점심 추천", session_id="t")
    body = agent.run("이거 저장해줘", session_id="t")["response"]
    assert body["saved_plan"]["start_time"] == "12:00:00" and body["saved_plan"]["plan_date"] == TODAY.isoformat()
    assert any("오늘" in a for a in body["save_result"]["assumptions"])
