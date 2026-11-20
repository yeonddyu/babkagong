"""같은 지역에서 늘 같은 식당만 추천되던 문제: Agent 는 요청마다 다른 seed 로 후보를 고르게 섞어 고른다."""
from __future__ import annotations

from app.agent.graph import MainAgent
from tests.unit.agent_fixtures import TODAY, make_registry, make_session


def _capture(registry):
    calls = []
    original = registry.invoke

    def invoke(name, arguments=None):
        if name == "search_restaurant_candidates":
            calls.append(dict(arguments))
        return original(name, arguments)

    registry.invoke = invoke
    return calls


def test_agent_requests_varied_candidates_with_new_seed_each_request(make_settings):
    registry = make_registry(make_settings, make_session())
    calls = _capture(registry)
    seeds = iter([11, 22])
    agent = MainAgent(registry, today_fn=lambda: TODAY, seed_fn=lambda: next(seeds))
    agent.run("강남역 12시 점심 먹고 카공")
    agent.run("강남역 12시 점심 먹고 카공")
    assert [c["order"] for c in calls] == ["varied", "varied"]
    assert [c["seed"] for c in calls] == [11, 22]


def test_same_seed_gives_same_recommendations(make_settings):
    def names(seed):
        agent = MainAgent(make_registry(make_settings, make_session()), today_fn=lambda: TODAY, seed_fn=lambda: seed)
        return [r["name"] for r in agent.run("강남역 12시 점심 먹고 카공")["response"]["recommendations"]]

    first = names(5)
    assert first and first == names(5)  # 실행 로그의 seed 로 재현 가능


def test_short_walk_request_keeps_nearest_first(make_settings):
    registry = make_registry(make_settings, make_session())
    calls = _capture(registry)
    MainAgent(registry, today_fn=lambda: TODAY, seed_fn=lambda: 1).run("강남역 12시 점심, 많이 걷기는 싫어")
    assert calls[0]["order"] == "distance" and "seed" not in calls[0]
