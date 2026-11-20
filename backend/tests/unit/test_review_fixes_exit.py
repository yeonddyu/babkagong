"""Codex 2차 검증 결함 4: 출구 파싱·매칭 엄격화, 실제 거리 기준점 일관 표시."""
from __future__ import annotations

from app.agent.analysis import parse_exit
from app.agent.graph import MainAgent
from app.datasets.exits import match_exit
from tests.unit.agent_fixtures import TODAY, make_registry, make_session
from tests.unit.test_f3002_restaurant_candidates import rt_row
from tests.unit.test_station_exits import EXIT_11, doc, kakao_with_exits

LINES = ("2호선", "신분당선")


def test_parse_exit_does_not_take_digits_from_longer_number():
    assert parse_exit("강남역 120번 출구 근처 점심") is None
    assert parse_exit("강남역 11번 출구 근처") == 11 and parse_exit("선릉역 2번출구") == 2


def test_match_exit_rejects_fake_names_and_categories():
    assert match_exit([doc("강남역가짜 11번출구")], "강남역", 11, LINES) is None  # 역 이름 뒤 공백 없음
    assert match_exit([doc("강남역 2호선 11번출구", cat="교통,수송 > 가짜지하철출구")], "강남역", 11, LINES) is None
    assert match_exit([doc("강남역 7호선 11번출구")], "강남역", 11, LINES) is None  # 그 역의 노선이 아님
    assert match_exit([doc("강남역 11번출구")], "강남역", 11, LINES)["name"] == "강남역 11번출구"  # 노선 표기 없이도 허용
    assert match_exit([doc("선릉역 분당선 3번출구")], "선릉역", 3, ("2호선", "수인분당선")) is not None  # 노선 별칭


def run(make_settings, msg, rows=None):
    session = make_session(kakao=kakao_with_exits({"강남역 2호선 11번출구": EXIT_11}), rt_rows=rows)
    return MainAgent(make_registry(make_settings, session), today_fn=lambda: TODAY, seed_fn=lambda: 1).run(msg)


def test_missing_exit_uses_station_center_everywhere(make_settings):
    r = run(make_settings, "강남역 13번 출구에서 500m 이내 12시 점심")["response"]
    assert r["origin"]["kind"] == "station" and r["origin"]["label"] == "강남역"
    assert r["recommendations"] and all(x["distance_from"] == "강남역" for x in r["recommendations"])
    assert "거리: 강남역에서 직선 500m 이내" in r["criteria"]
    assert "거리 기준점: 강남역 중심 (13번 출구를 찾지 못함)" in r["criteria"]
    assert not any("13번 출구에서" in c for c in r["criteria"])
    assert any("13번 출구를 찾지 못했습니다" in n for n in r["notices"])
    assert "강남역에서 직선" in r["summary"]


def test_found_exit_criteria_name_the_exit(make_settings):
    r = run(make_settings, "강남역 11번 출구에서 300m 이내 12시 점심")["response"]
    assert "거리 기준점: 강남역 11번 출구 (카카오 로컬 출구 좌표)" in r["criteria"]
    assert "거리: 강남역 11번 출구에서 직선 300m 이내" in r["criteria"]
    assert not any("출구" in n for n in r["notices"])


def test_adjacent_replan_reports_the_origin_actually_used(make_settings):
    # 강남역 후보는 예산 초과 → 인접 역 재계획 (신논현역 후보 없음 → 역삼역)
    from tests.unit.agent_fixtures import YEOKSAM

    rows = [rt_row(2, "스시하우스", 37.4983, 127.0279, cat="일식")] + YEOKSAM
    r = run(make_settings, "강남역 11번 출구 근처 9천원 이하 점심", rows)
    body = r["response"]
    assert [x["area"] for x in body["recommendations"]] == ["역삼역"]
    assert body["origin"]["label"] == "역삼역" and body["origin"]["kind"] == "station"  # 지도 기준점도 실제 역
    assert body["recommendations"][0]["distance_from"] == "역삼역"
    basis = next(c for c in body["criteria"] if c.startswith("거리 기준점"))
    assert basis.startswith("거리 기준점: 강남역 11번 출구") and "인접 역 재계획" in basis and "역삼역 중심" in basis
