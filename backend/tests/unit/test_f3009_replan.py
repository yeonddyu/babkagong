"""F3009 재계획 - 단위 테스트 (Mock 외부 API)."""
from __future__ import annotations

from collections import Counter

from app.agent.graph import MainAgent
from tests.unit.agent_fixtures import GANGNAM, TODAY, YEOKSAM, make_registry, make_session
from tests.unit.test_f3002_restaurant_candidates import rt_row


def agent(make_settings, session, **kw):
    return MainAgent(make_registry(make_settings, session, **{k: v for k, v in kw.items() if k != "max_replans"}),
                     today_fn=lambda: TODAY, seed_fn=lambda: 0, max_replans=kw.get("max_replans", 3))


def fresh_calls(result):
    return [(c["tool"], str(sorted(c["args"].items()))) for c in result["tool_calls"] if not c["reused"]]


def test_graph_has_replan_node(make_settings):
    s = agent(make_settings, make_session()).graph_structure()
    assert "replan" in s["nodes"] and "judge->replan" in s["edges"] and "replan->execute" in s["edges"]


def test_no_replan_when_satisfied(make_settings):
    r = agent(make_settings, make_session()).run("강남역 점심 추천")
    assert r["replans"] == [] and r["evaluation"].satisfied


def test_replan_next_batch_reuses_results(make_settings):
    # 앞쪽 10곳(첫 상세 묶음)은 메뉴가 없고 그다음 곳들만 메뉴가 있는 상황 → 1회 재계획으로 다음 묶음 조회
    rows = [rt_row(100 + i, f"메뉴없음{i}", 37.49795 + i * 0.00002, 127.02762) for i in range(10)] + GANGNAM[6:]
    session = make_session(rt_rows=rows)
    r = agent(make_settings, session).run("강남역 1만 1천원 이하 점심")
    assert [h["strategy"] for h in r["replans"]] == ["next_batch"]
    assert [e.name for e in r["evaluation"].satisfied] == ["냉면명가", "칼국수집"]
    calls = fresh_calls(r)
    assert all(n == 1 for n in Counter(calls).values())  # 같은 Tool·같은 입력 재호출 없음
    assert sum(1 for t, _ in calls if t == "search_restaurant_candidates") == 1
    # 레드테이블 12곳 + 인허가 보충 1곳 = 13곳, 각 1회씩만 조회
    assert sum(1 for t, _ in calls if t == "get_restaurant_details") == 13


def test_replan_adjacent_area(make_settings):
    # 강남역 후보는 모두 예산 초과, 역삼역에 예산 이하 후보 존재. 강남역에서 가까운 순: 신논현역(후보 없음) → 역삼역
    rows = [rt_row(2, "스시하우스", 37.4983, 127.0279, cat="일식")] + YEOKSAM
    r = agent(make_settings, make_session(rt_rows=rows)).run("강남역 9천원 이하 점심")
    strategies = [h["strategy"] for h in r["replans"]]
    assert strategies == ["adjacent_area", "adjacent_area"]
    assert [e.name for e in r["evaluation"].satisfied] == ["역삼 백반"]
    assert r["data"].areas_searched == ["강남역", "신논현역", "역삼역"]


def test_replan_limit_reached_stops_with_reason(make_settings):
    # 후보 30곳 모두 가격 미확인 → 다음 묶음 재계획이 계속 필요하지만 상한 3회에서 멈춤
    rows = [rt_row(200 + i, f"미확인{i}", 37.4981 + i * 0.00002, 127.0277) for i in range(30)]
    r = agent(make_settings, make_session(rt_rows=rows, menus=[])).run("강남역 1만원 이하 점심")
    assert len(r["replans"]) == 3 and r["evaluation"].satisfied == []
    assert r["stop_reason"] == "재계획 상한(3회)에 도달"
    assert len(fresh_calls(r)) == len(set(fresh_calls(r)))


def test_missing_key_is_not_replanned(make_settings):
    r = agent(make_settings, make_session(), redtable=None, seoul=None).run("강남역 점심 추천")
    assert r["replans"] == []
    assert "MISSING_API_KEY" in r["stop_reason"]


def test_no_alternative_stops(make_settings):
    """2km 안 서비스 역을 가까운 순으로 모두 찾은 뒤에야 '대안 없음' 으로 멈춘다 (상한을 넉넉히 둔 경우)."""
    from app.agent.graph import MainAgent
    from app.datasets.stations import StationDirectory
    from tests.unit.agent_fixtures import TODAY, make_registry

    rows = [rt_row(2, "스시하우스", 37.4983, 127.0279, cat="일식")]
    r = MainAgent(make_registry(make_settings, make_session(rt_rows=rows)), today_fn=lambda: TODAY, max_replans=10).run("강남역 5천원 이하 점심")
    strategies = [h["strategy"] for h in r["replans"]]
    from app.core.geo import haversine_m

    g = StationDirectory().get("강남역")
    within_2km = {s.name for s in StationDirectory().stations()
                  if s.name != "강남역" and haversine_m(g.latitude, g.longitude, s.latitude, s.longitude) <= 2000}
    assert strategies[-1] == "none" and set(strategies[:-1]) == {"adjacent_area"}
    assert set(r["data"].areas_searched) == {"강남역"} | within_2km  # 2km 안 역을 모두 찾은 뒤 멈춤
    assert r["stop_reason"] == "탐색 가능한 대안이 없음"
