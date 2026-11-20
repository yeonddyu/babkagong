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


def test_pressed_station_wins_over_previous_conversation_area(make_settings):
    """강남역으로 추천받은 뒤 '선릉역' 버튼을 누르고 역 이름 없이 보내면 선릉역에서 찾는다."""
    agent = MainAgent(make_registry(make_settings, make_session()), today_fn=lambda: TODAY)
    first = agent.run("강남역 12시 점심 먹고 카공", area_hint="강남역")
    second = agent.run("점심 먹고 카공하고 싶어", session_id=first["session_id"], area_hint="선릉역")
    assert second["response"]["conditions"]["preference"]["area"] == "선릉역"
    assert second["data"].areas_searched[0] == "선릉역"  # 첫 검색이 선릉역 (가짜 데이터엔 선릉역 식당이 없어 이후 인접 역 재계획)
    # 버튼을 그대로 두고 조건만 바꾸는 후속 요청은 이전 조건(12시 등)을 이어받는다
    follow = agent.run("1만원 이하로", session_id=first["session_id"], area_hint="선릉역")
    assert follow["response"]["conditions"]["preference"]["area"] == "선릉역"
    assert follow["response"]["conditions"]["base"]["meal_time"] == "12:00:00"
    # 메시지에 역을 직접 말하면 버튼보다 메시지가 우선
    named = agent.run("역삼역에서 점심", session_id=first["session_id"], area_hint="선릉역")
    assert named["response"]["conditions"]["preference"]["area"] == "역삼역"
