"""역 출구 좌표 데이터셋 (카카오 로컬 키워드 검색 → 정확히 일치하는 '지하철출구' 장소만).

- 질의: '{역} {번호}번출구', 역 중심 반경 800m. 사용자가 말한 (역, 번호) 만 그때 조회해 결과를 쌓는다
- 채택 조건: 분류가 '지하철출구' 로 끝나고, 이름이 '{역}' 로 시작해 ' {번호}번출구' 로 끝나는 장소가 정확히 1곳
  (예: '강남역 2호선 11번출구', '강남역 신분당선 4번출구'). 0곳이거나 여러 곳이면 그 번호는 저장하지 않는다.
- 출구 좌표는 거리 계산의 기준점으로만 쓰며, 식당·카페 ID 와 연결하지 않는다.
"""
from __future__ import annotations

from typing import Any

from app.clients.kakao_local import KakaoLocalClient
from app.core.errors import ExternalAPIError
from app.core.geo import STATIONS
from app.datasets.cache import JsonCache

SOURCE_KAKAO_EXIT = "kakao_local_keyword"
EXIT_SEARCH_RADIUS_M = 800


def match_exit(documents: list[dict[str, Any]], station: str, number: int) -> dict[str, Any] | None:
    hits = [d for d in documents
            if str(d.get("category_name", "")).endswith("지하철출구")
            and str(d.get("place_name", "")).startswith(station)
            and str(d.get("place_name", "")).endswith(f" {number}번출구")]
    if len(hits) != 1:
        return None
    d = hits[0]
    try:
        lat, lng = float(d["y"]), float(d["x"])
    except (KeyError, TypeError, ValueError):
        return None
    return {"number": number, "name": d["place_name"], "latitude": lat, "longitude": lng,
            "place_id": str(d.get("id") or ""), "place_url": d.get("place_url") or None}


class StationExitDataset:
    """역 출구 좌표. 서울 전역 역마다 미리 모으지 않고, 요청한 (역, 번호) 만 조회해 결과(없음 포함)를 캐시에 쌓는다."""

    CACHE_NAME = "station_exits_v2"

    def __init__(self, client: KakaoLocalClient, cache: JsonCache, stations=None):
        self.client = client
        self.cache = cache
        self.stations = stations  # StationDirectory (역 좌표)

    def _table(self) -> dict[str, dict[str, Any]]:
        payload = self.cache.load(self.CACHE_NAME)
        return dict(payload["data"]) if payload else {}

    def find(self, station: str, number: int) -> tuple[dict[str, Any] | None, str | None]:
        """(출구, 못 찾은 사유). 조회 실패는 예외 대신 사유로 돌려준다."""
        table = self._table()
        key = f"{station}|{number}"
        if key not in table:
            st = self.stations.get(station) if self.stations is not None else None
            lat, lng = (st.latitude, st.longitude) if st else STATIONS.get(station, (None, None))
            if lat is None:
                return None, f"{station} 위치를 알 수 없어 출구를 찾지 못했습니다"
            query_name = station.split("(")[0]
            try:
                page = self.client.search_keyword(f"{query_name} {number}번출구", lat=lat, lng=lng, radius_m=EXIT_SEARCH_RADIUS_M)
            except ExternalAPIError as exc:
                return None, f"출구 위치를 조회하지 못했습니다({exc.code.value})"
            table[key] = match_exit(page.documents, query_name, number)
            self.cache.save(self.CACHE_NAME, table, source=SOURCE_KAKAO_EXIT)
        hit = table[key]
        if hit is None:
            return None, f"{station} {number}번 출구를 찾지 못했습니다"
        return hit, None
