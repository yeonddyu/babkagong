"""서비스 역 목록 — 역삼역(SSAFY) 과 가까운 역 5곳, 모두 6곳.

- 좌표: 강남역·역삼역은 기존 서비스 기준 좌표, 나머지는 서울 열린데이터광장 '서울시 역사마스터 정보'(subwayStationMaster,
  2026-11-20 조회) 에서 같은 역의 노선별 좌표를 평균한 값.
- 역삼역에서 직선거리: 언주 775m, 강남 834m, 신논현 1,098m, 선릉 1,150m, 선정릉 1,278m.
- 목록이 고정이라 실행 중 외부 호출을 하지 않는다. 다른 역 이름은 서비스 지역이 아니다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.core.geo import haversine_m

SERVICE_STATIONS: dict[str, tuple[float, float, tuple[str, ...]]] = {
    "역삼역": (37.500622, 127.036456, ("2호선",)),
    "강남역": (37.497952, 127.027619, ("2호선", "신분당선")),
    "언주역": (37.507287, 127.033868, ("9호선",)),
    "신논현역": (37.504598, 127.025060, ("9호선", "신분당선")),
    "선릉역": (37.504571, 127.048505, ("2호선", "수인분당선")),
    "선정릉역": (37.510516, 127.043838, ("수인분당선", "9호선")),
}
BUILTIN = {name: (lat, lng) for name, (lat, lng, _) in SERVICE_STATIONS.items()}
AREA_DATA_RADIUS_M = 1500  # 저장할 외부 데이터 범위: 서비스 역 중 하나에서 이 거리 안

# 이름만 말했을 때 역으로 인정하는 뒷말 (예: '선릉에서', '언주 근처')
BARE_SUFFIX = r"(?=\s*(?:역|에서|근처|주변|부근|쪽|앞|일대|인근))"


@dataclass(frozen=True)
class Station:
    name: str  # 표시 이름 (예: '선릉역')
    base: str  # 역 없이 부르는 이름 (예: '선릉')
    lines: tuple[str, ...]
    latitude: float
    longitude: float

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "base": self.base, "lines": list(self.lines), "latitude": self.latitude, "longitude": self.longitude}


def _base(name: str) -> str:
    n = re.sub(r"\s*\(.*?\)\s*", "", name).strip()
    return n[:-1] if n.endswith("역") and len(n) > 2 else n


def within_service_area(lat: float, lng: float, radius_m: float = AREA_DATA_RADIUS_M) -> bool:
    return any(haversine_m(lat, lng, s_lat, s_lng) <= radius_m for s_lat, s_lng in BUILTIN.values())


class StationDirectory:
    """서비스 역 6곳. 인자는 예전 호출 형태와 맞추기 위한 것으로 쓰지 않는다 (외부 호출 없음)."""

    def __init__(self, *_args: Any, **_kwargs: Any):
        self._items = [Station(n, _base(n), lines, lat, lng) for n, (lat, lng, lines) in SERVICE_STATIONS.items()]

    def stations(self) -> list[Station]:
        return list(self._items)

    def names(self) -> list[str]:
        return [s.name for s in self._items]

    def refresh(self) -> bool:
        return True  # 고정 목록

    def get(self, name: str | None, *, refresh: bool = False) -> Station | None:  # noqa: ARG002 - 예전 호출 호환
        if not name:
            return None
        base = _base(name.strip())
        return next((s for s in self._items if s.name == name.strip() or s.base == base), None)

    def find_in_text(self, text: str) -> Station | None:
        """발화에서 서비스 역을 찾는다. 'OO역' 이 먼저, 그다음 'OO에서/근처' 같은 이름만 쓴 표현. 긴 이름 우선."""
        items = sorted(self._items, key=lambda s: -len(s.base))  # '신논현'·'선정릉' 이 먼저
        for s in items:
            if re.search(rf"(?<![가-힣]){re.escape(s.base)}\s*역", text):
                return s
        for s in items:
            if s.base in ("강남", "역삼") and re.search(rf"(?<![가-힣]){s.base}", text):
                return s  # 기존 동작 유지: '강남', '역삼' 은 이름만 있어도 인정
            if re.search(rf"(?<![가-힣]){re.escape(s.base)}{BARE_SUFFIX}", text):
                return s
        return None

    def mentioned_other_station(self, text: str) -> str | None:
        """서비스 역이 아닌 'OO역' 을 말했으면 그 이름 (안내용)."""
        for m in re.finditer(r"([가-힣A-Za-z0-9]{1,10})역", text):
            word = m.group(1)
            if word in ("지하철", "전철", "기차", "버스", "근처", "주변", "지") or self.get(word):
                continue
            return f"{word}역"
        return None

    def nearest_other(self, name: str, max_m: float = 2000, exclude: set[str] | frozenset[str] = frozenset()) -> Station | None:
        """name 에서 가장 가까운 다른 서비스 역 (exclude 에 있는 역은 건너뜀)."""
        here = self.get(name)
        if here is None:
            return None
        others = [(haversine_m(here.latitude, here.longitude, s.latitude, s.longitude), s) for s in self._items
                  if s.name != here.name and s.name not in exclude]
        others = [t for t in others if t[0] <= max_m]
        return min(others, key=lambda t: t[0])[1] if others else None
