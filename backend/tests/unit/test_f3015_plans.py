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


def test_save_with_chosen_cafe_and_coordinates(make_settings, repo):
    agent = MainAgent(make_registry(make_settings, make_session()), today_fn=lambda: TODAY,
                      memory=InMemoryMemoryStore(), plan_repo=repo)
    first = agent.run("내일 12시 강남역 1만원 이하 점심 먹고 카공", session_id="c")["response"]["recommendations"][0]
    saved = agent.run("1번 코스 저장해줘 (카페 2번)", session_id="c")["response"]["saved_plan"]
    assert saved["cafe_name"] == first["cafes"][1]["name"]
    assert saved["restaurant_lat"] == first["latitude"] and saved["cafe_lat"] == first["cafes"][1]["latitude"]
    saved2 = agent.run("카페 3번으로 1번 코스 저장", session_id="c")["response"]["saved_plan"]
    assert saved2["cafe_name"] == first["cafes"][2]["name"] and saved2["restaurant_name"] == first["name"]


def test_old_db_file_gets_new_columns(tmp_path):
    """좌표 컬럼이 없던 이전 DB 파일도 데이터를 유지한 채 보강된다."""
    import sqlite3

    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE plans (id INTEGER PRIMARY KEY, title VARCHAR(100) NOT NULL, plan_date DATE NOT NULL, "
                "start_time TIME NOT NULL, end_time TIME NOT NULL, area VARCHAR(10), restaurant_name VARCHAR(200) NOT NULL, "
                "restaurant_source VARCHAR(64), restaurant_source_id VARCHAR(64), restaurant_address VARCHAR(300), "
                "cafe_name VARCHAR(200), cafe_source VARCHAR(64), cafe_source_id VARCHAR(64), cafe_address VARCHAR(300), "
                "cafe_url VARCHAR(500), memo TEXT, session_id VARCHAR(64), created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)")
    con.execute("INSERT INTO plans VALUES (1,'옛 계획','2026-11-20','12:00:00.000000','13:00:00.000000',NULL,'식당',NULL,NULL,NULL,"
                "NULL,NULL,NULL,NULL,NULL,NULL,NULL,'2026-11-19 10:00:00','2026-11-19 10:00:00')")
    con.commit()
    con.close()
    engine = make_engine(f"sqlite:///{path}")
    init_db(engine)
    r = PlanRepository(make_session_factory(engine))
    old = r.get(1)
    assert old.title == "옛 계획" and old.restaurant_lat is None
    p, _ = r.create(plan(restaurant_lat=37.4981, restaurant_lng=127.0277))
    assert r.get(p.id).restaurant_lat == 37.4981
