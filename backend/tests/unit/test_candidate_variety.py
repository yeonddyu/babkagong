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


def test_walk_limit_converted_to_search_radius(make_settings):
    """'도보 3분 이내'·'200m 이내' 는 판정과 같은 추정식으로 반경을 줄여 그 안에서 고른다."""
    registry = make_registry(make_settings, make_session())
    calls = _capture(registry)
    agent = MainAgent(registry, today_fn=lambda: TODAY, seed_fn=lambda: 1)
    agent.run("강남역에서 도보 3분 이내로 점심")
    agent.run("강남역 200m 이내 점심", session_id="s2")
    agent.run("강남역 점심", session_id="s3")
    assert calls[0]["radius_m"] == 154  # 3분 × 67m/분 ÷ 1.3
    assert calls[1]["radius_m"] == 200
    assert "radius_m" not in calls[2]  # 제한이 없으면 기본 700m


def test_keeps_checking_next_batch_until_enough_satisfied(make_settings):
    """첫 10곳 중 1곳만 충족하면, 남은 후보를 이어서 확인해 추천 수를 채운다 (재계획 아님)."""
    from tests.unit.test_f3002_restaurant_candidates import rt_row

    rows = [rt_row(100 + i, f"식당{i:02d}", 37.497952 + i * 0.0001, 127.027619) for i in range(16)]
    menus = [{"MENU_ID": n, "MENU_NM": "백반", "MENU_PRICE": 9000, "RSTR_ID": rid}
             for n, rid in enumerate([100, 111, 112, 113, 114], 1)]  # 첫 10곳 중 1곳 + 그 뒤 4곳만 메뉴
    registry = make_registry(make_settings, make_session(rt_rows=rows, menus=menus))
    # '걷기 싫어' → 가까운 순(distance)이라 첫 묶음이 정확히 식당00~09
    body = MainAgent(registry, today_fn=lambda: TODAY, seed_fn=lambda: 1).run(
        "강남역 12시 점심 1만원 이하, 많이 걷기는 싫어")["response"]
    assert {r["name"] for r in body["recommendations"]} == {"식당00", "식당11", "식당12", "식당13", "식당14"}
    assert body["replans"] == []
