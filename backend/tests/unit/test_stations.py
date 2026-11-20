"""서비스 역 6곳 (역삼역과 가까운 역) 과 발화에서 역 찾기."""
from __future__ import annotations

from app.agent.graph import MainAgent
from app.core.geo import haversine_m
from app.datasets.stations import SERVICE_STATIONS, StationDirectory, within_service_area
from tests.unit.agent_fixtures import TODAY, make_registry, make_session

D = StationDirectory()


def test_six_stations_all_within_1_3km_of_yeoksam():
    assert D.names() == ["역삼역", "강남역", "언주역", "신논현역", "선릉역", "선정릉역"]
    y = SERVICE_STATIONS["역삼역"][:2]
    assert all(haversine_m(*y, s.latitude, s.longitude) <= 1300 for s in D.stations())


def test_find_in_text():
    f = lambda t: (s := D.find_in_text(t)) and s.name  # noqa: E731
    assert f("선릉역 근처 점심") == "선릉역"
    assert f("선정릉역 점심") == "선정릉역"  # '선릉' 과 헷갈리지 않음
    assert f("신논현역에서 점심") == "신논현역"
    assert f("언주 근처 점심 먹고 카공") == "언주역"  # 역 없이 이름 + 근처
    assert f("강남 점심") == "강남역" and f("역삼에서 점심") == "역삼역"  # 기존 동작 유지
    assert f("홍대입구역 점심") is None
    assert f("점심 추천해줘") is None


def test_unsupported_station_is_named():
    assert D.mentioned_other_station("홍대입구역 근처 점심") == "홍대입구역"
    assert D.mentioned_other_station("선릉역 점심") is None
    assert D.mentioned_other_station("지하철역 근처 점심") is None


def test_get_nearest_and_area():
    assert D.get("선릉").name == "선릉역" and D.get("없는역") is None
    assert D.nearest_other("역삼역").name == "언주역"  # 775m
    assert within_service_area(37.5006, 127.0364) and not within_service_area(37.5568, 126.9237)  # 홍대입구 X


def test_other_station_gets_clarify_with_reason(make_settings):
    agent = MainAgent(make_registry(make_settings, make_session()), today_fn=lambda: TODAY)
    body = agent.run("홍대입구역 근처 점심 먹고 카공")["response"]
    assert body["clarify"] is True and body["recommendations"] == []
    assert body["message"].startswith("홍대입구역은(는) 서비스 지역이 아니에요.")
    assert "선정릉" in body["message"]
