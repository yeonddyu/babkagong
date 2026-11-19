"""F3016 계획 수정 및 삭제 - 단위 테스트."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest
from pydantic import ValidationError

from app.datasets.cache import KST
from app.storage.db import init_db, make_engine, make_session_factory
from app.storage.plans import PlanCreate, PlanNotFound, PlanRepository, PlanUpdate


@pytest.fixture
def repo():
    engine = make_engine("sqlite://")
    init_db(engine)
    t = {"now": datetime(2026, 11, 19, 10, tzinfo=KST)}

    def clock():
        t["now"] += timedelta(minutes=1)
        return t["now"]

    return PlanRepository(make_session_factory(engine), clock=clock)


def mk(repo, title="A", s=time(12), e=time(15), d=date(2026, 11, 20)):
    return repo.create(PlanCreate(title=title, plan_date=d, start_time=s, end_time=e, restaurant_name="식당"))[0]


def test_update_core_values_reflected(repo):
    p = mk(repo)
    updated, conflicts = repo.update(p.id, PlanUpdate(plan_date=date(2026, 11, 21), start_time=time(18), end_time=time(20), title="저녁"))
    assert (updated.plan_date, updated.start_time, updated.end_time, updated.title) == (date(2026, 11, 21), time(18), time(20), "저녁")
    assert updated.restaurant_name == "식당" and updated.created_at == p.created_at and updated.updated_at > p.updated_at
    assert repo.get(p.id).title == "저녁" and conflicts == []


def test_update_reports_overlap(repo):
    a = mk(repo, "A", time(12), time(13))
    b = mk(repo, "B", time(14), time(15))
    _, conflicts = repo.update(b.id, PlanUpdate(start_time=time(12, 30)))
    assert [c.id for c in conflicts] == [a.id]


def test_update_invalid_time_rejected(repo):
    p = mk(repo)
    with pytest.raises(ValidationError):
        repo.update(p.id, PlanUpdate(end_time=time(11)))
    assert repo.get(p.id).end_time == time(15)  # 변경 없음


def test_delete_reflected(repo):
    a, b = mk(repo, "A"), mk(repo, "B", d=date(2026, 11, 22))
    repo.delete(a.id)
    assert [p.id for p in repo.list()] == [b.id]
    with pytest.raises(PlanNotFound):
        repo.delete(a.id)
    with pytest.raises(PlanNotFound):
        repo.update(a.id, PlanUpdate(title="x"))
