"""Codex 2차 검증 결함 8: 카카오 출구 정보는 디스크에 저장하지 않고 메모리에서만 짧게 재사용."""
from __future__ import annotations

from app.datasets.exits import StationExitDataset
from app.datasets.stations import StationDirectory


class Kakao:
    def __init__(self):
        self.calls = 0

    def search_keyword(self, query, **_):
        self.calls += 1
        doc = {"id": "999", "place_name": "강남역 2호선 11번출구", "category_name": "교통,수송 > 지하철,전철 > 지하철출구",
               "x": "127.0262", "y": "37.4990", "place_url": "http://place.map.kakao.com/999"}
        return type("Page", (), {"documents": [doc]})()


def test_exit_lookup_not_written_to_disk_and_refreshed_after_ttl(tmp_path):
    now = [0.0]
    kakao = Kakao()
    ds = StationExitDataset(kakao, None, StationDirectory(), clock=lambda: now[0])
    hit, _ = ds.find("강남역", 11)
    assert hit["name"] == "강남역 2호선 11번출구" and "place_id" not in hit  # 장소 ID 보관 안 함
    ds.find("강남역", 11)
    assert kakao.calls == 1  # 같은 프로세스 안에서는 재사용
    now[0] += StationExitDataset.CACHE_TTL_SEC + 1
    ds.find("강남역", 11)
    assert kakao.calls == 2  # 시간이 지나면 다시 조회해 최신 유지
    assert list(tmp_path.iterdir()) == []


def test_catalog_exit_lookup_leaves_no_cache_file(make_settings, tmp_path):
    """실제 Agent 흐름으로 출구를 찾은 뒤에도 캐시 디렉터리에 출구(카카오) 파일이 없다."""
    from app.agent.graph import MainAgent
    from tests.unit.agent_fixtures import TODAY, make_registry, make_session
    from tests.unit.test_station_exits import EXIT_11, kakao_with_exits

    registry = make_registry(make_settings, make_session(kakao=kakao_with_exits({"강남역 2호선 11번출구": EXIT_11})))
    body = MainAgent(registry, today_fn=lambda: TODAY).run("강남역 11번 출구 근처 12시 점심")["response"]
    assert body["origin"]["kind"] == "exit"  # 출구를 실제로 찾았음
    cache_dir = tmp_path / "cache"
    assert cache_dir.exists()  # 다른 데이터셋 캐시는 생김
    assert not [p.name for p in cache_dir.iterdir() if "exit" in p.name]
