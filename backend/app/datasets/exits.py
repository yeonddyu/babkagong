"""역 출구 좌표 데이터셋 (카카오 로컬 키워드 검색 → 정확히 일치하는 '지하철출구' 장소만).

- 질의: '{역} {번호}번출구', 역 중심 반경 800m. 사용자가 말한 (역, 번호) 만 그때 조회해 결과를 쌓는다
- 채택 조건: 분류의 마지막 요소가 정확히 '지하철출구' 이고, 이름이 '{역} {번호}번출구' 또는 '{역} {노선} {번호}번출구'
  (노선은 그 역의 노선 표기만 허용, 예: '강남역 2호선 11번출구', '강남역 신분당선 4번출구') 인 장소가 정확히 1곳.
  0곳이거나 여러 곳이면 출구를 찾지 못한 것으로 본다.
- 출구 좌표는 거리 계산의 기준점으로만 쓰며, 식당·카페 ID 와 연결하지 않는다.
"""
from __future__ import annotations

import re
from typing import Any

from app.clients.kakao_local import KakaoLocalClient
from app.core.errors import ExternalAPIError
from app.core.geo import STATIONS
from app.datasets.cache import JsonCache

SOURCE_KAKAO_EXIT = "kakao_local_keyword"
EXIT_SEARCH_RADIUS_M = 800


# 카카오 장소 이름에 쓰이는 노선 표기 (역 목록의 노선명 → 허용 표기)
LINE_ALIASES = {"수인분당선": ("수인분당선", "분당선"), "분당선": ("분당선", "수인분당선")}


def match_exit(documents: list[dict[str, Any]], station: str, number: int,
               lines: tuple[str, ...] | list[str] = ()) -> dict[str, Any] | None:
    allowed = sorted({a for ln in lines for a in LINE_ALIASES.get(ln, (ln,))}, key=len, reverse=True)
    line_part = f"(?:(?:{'|'.join(re.escape(a) for a in allowed)}) )?" if allowed else ""
    name_ok = re.compile(rf"^{re.escape(station)} {line_part}{number}번출구$")
    hits = [d for d in documents
            if str(d.get("category_name", "")).split(">")[-1].strip() == "지하철출구"
            and name_ok.match(str(d.get("place_name", "")).strip())]
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
            table[key] = match_exit(page.documents, query_name, number, st.lines if st else ())
            self.cache.save(self.CACHE_NAME, table, source=SOURCE_KAKAO_EXIT)
        hit = table[key]
        if hit is None:
            return None, f"{station} {number}번 출구를 찾지 못했습니다"
        return hit, None
