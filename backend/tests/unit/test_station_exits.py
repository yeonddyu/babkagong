"""'N번 출구 근처' — 카카오 로컬의 지하철출구 장소 좌표를 거리 기준점으로 쓴다 (Mock)."""
from __future__ import annotations

from app.agent.analysis import parse_exit
from app.agent.graph import MainAgent
from app.datasets.exits import match_exit
from tests.fakes import json_response
from tests.unit.agent_fixtures import TODAY, kakao_handler, make_registry, make_session

EXIT_11 = (37.4986, 127.0282)  # 가짜 좌표 (가짜 식당들 사이)


def doc(name, cat="교통,수송 > 지하철,전철 > 지하철출구", lat=EXIT_11[0], lng=EXIT_11[1]):
    return {"id": "1", "place_name": name, "category_name": cat, "x": str(lng), "y": str(lat), "place_url": "http://place.map.kakao.com/1"}


def kakao_with_exits(exits: dict[str, tuple[float, float]]):
    """키워드 검색은 등록한 출구만 돌려주고, 카테고리(카페) 검색은 기존 가짜 응답을 쓴다."""
    cafes = kakao_handler()

    def handler(url, params, headers):
        if "keyword" in url:
            q = params["query"]
            st, num = q.split()[0], q.split()[1].replace("번출구", "")
            name = f"{st} 2호선 {num}번출구"
            if name in exits:
                return json_response({"meta": {"total_count": 1, "pageable_count": 1, "is_end": True},
                                      "documents": [doc(name, lat=exits[name][0], lng=exits[name][1]), doc(f"{st}{num}번출구약국", cat="의료,건강 > 약국")]})
            return json_response({"meta": {"total_count": 0, "pageable_count": 0, "is_end": True}, "documents": []})
        return cafes(url, params, headers)
    return handler


def test_parse_exit():
    assert parse_exit("강남역 11번 출구 근처 점심") == 11
    assert parse_exit("역삼역 3번출구 앞에서 먹고 카공") == 3
    assert parse_exit("강남역 점심 11시") is None
    assert parse_exit("1번 출구나 2번 출구 근처") is None  # 기준점이 둘이면 정하지 않음


def test_match_exit_requires_exact_subway_exit():
    docs = [doc("강남역 2호선 11번출구"), doc("강남역11번출구약국", cat="의료,건강 > 약국"), doc("강남역 2호선 1번출구")]
    lines = ("2호선", "신분당선")
    hit = match_exit(docs, "강남역", 11, lines)
    assert hit["name"] == "강남역 2호선 11번출구" and hit["latitude"] == EXIT_11[0]
    assert match_exit(docs, "강남역", 1, lines)["name"] == "강남역 2호선 1번출구"  # '11번출구' 와 섞이지 않음
    assert match_exit(docs, "강남역", 13, lines) is None
    assert match_exit([doc("강남역 2호선 4번출구"), doc("강남역 신분당선 4번출구")], "강남역", 4, lines) is None  # 여러 곳이면 판단 안 함


def run(make_settings, msg, exits):
    agent = MainAgent(make_registry(make_settings, make_session(kakao=kakao_with_exits(exits))),
                      today_fn=lambda: TODAY, seed_fn=lambda: 1)
    return agent.run(msg)["response"]


def test_distances_measured_from_requested_exit(make_settings):
    from app.core.geo import haversine_m

    body = run(make_settings, "강남역 11번 출구 근처 12시 점심", {"강남역 2호선 11번출구": EXIT_11})
    assert body["origin"]["kind"] == "exit" and body["origin"]["label"] == "강남역 11번 출구"
    assert "강남역 2호선 11번출구" in body["origin"]["source"]
    for r in body["recommendations"]:
        assert r["distance_from"] == "강남역 11번 출구"
        assert abs(r["distance_m"] - haversine_m(*EXIT_11, r["latitude"], r["longitude"])) <= 1
    assert any("11번 출구" in c for c in body["criteria"])
    assert "강남역 11번 출구에서 직선" in body["summary"]
    assert not any("출구" in n for n in body["notices"])  # 찾았으면 안내 없음


def test_unknown_exit_falls_back_to_station_with_notice(make_settings):
    body = run(make_settings, "강남역 13번 출구 근처 12시 점심", {"강남역 2호선 11번출구": EXIT_11})
    assert body["origin"]["kind"] == "station"
    assert body["recommendations"] and all(r["distance_from"] == "강남역" for r in body["recommendations"])
    notes = body["query_basis"]["notes"]
    assert any("13번 출구를 찾지 못했습니다" in n and "역 중심 기준" in n for n in notes)
    assert any("13번 출구를 찾지 못했습니다" in n for n in body["notices"])  # 화면에도 안내


def test_walk_limit_applies_from_exit(make_settings):
    body = run(make_settings, "강남역 11번 출구에서 100m 이내 12시 점심", {"강남역 2호선 11번출구": EXIT_11})
    assert body["recommendations"] and all(r["distance_m"] <= 100 for r in body["recommendations"])
    assert any(c["value"].startswith("강남역 11번 출구에서 직선") for r in body["recommendations"] for c in r["checks"] if c["criterion"] == "거리")
