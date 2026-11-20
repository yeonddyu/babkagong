"""역 출구 좌표 데이터셋 (카카오 로컬 키워드 검색 → 정확히 일치하는 '지하철출구' 장소만).

- 질의: '{역} {번호}번출구', 역 중심 반경 800m
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
MAX_EXIT_NUMBER = 14  # 이 번호까지 조회 (강남역 1~12, 역삼역 1~8 확인됨)
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
    CACHE_NAME = "station_exits"

    def __init__(self, client: KakaoLocalClient, cache: JsonCache):
        self.client = client
        self.cache = cache

    def _build(self):
        data: dict[str, dict[str, Any]] = {}
        for station, (lat, lng) in STATIONS.items():
            found: dict[str, Any] = {}
            for n in range(1, MAX_EXIT_NUMBER + 1):
                page = self.client.search_keyword(f"{station} {n}번출구", lat=lat, lng=lng, radius_m=EXIT_SEARCH_RADIUS_M)
                hit = match_exit(page.documents, station, n)
                if hit:
                    found[str(n)] = hit
            data[station] = found
        return data, {"source": SOURCE_KAKAO_EXIT}

    def load(self) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        payload = self.cache.get_or_build(self.CACHE_NAME, self._build)
        return payload["data"], {k: v for k, v in payload.items() if k != "data"}

    def find(self, station: str, number: int) -> tuple[dict[str, Any] | None, str | None]:
        """(출구, 못 찾은 사유). 조회 실패는 예외 대신 사유로 돌려준다."""
        try:
            data, _ = self.load()
        except ExternalAPIError as exc:
            return None, f"출구 위치를 조회하지 못했습니다({exc.code.value})"
        hit = data.get(station, {}).get(str(number))
        if hit is None:
            have = sorted(int(k) for k in data.get(station, {}))
            return None, f"{station} {number}번 출구를 찾지 못했습니다" + (f" (확인된 출구: {have[0]}~{have[-1]}번)" if have else "")
        return hit, None
