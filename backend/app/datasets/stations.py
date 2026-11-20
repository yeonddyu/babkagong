"""서울 지하철역 목록 (서비스 지역 = 역).

출처: 서울 열린데이터광장 '서울시 역사마스터 정보'(subwayStationMaster) — 역명(BLDN_NM)·노선(ROUTE)·위경도(LAT, LOT).
- 한 행은 '역 × 노선'. 같은 이름이고 500m 안에 있는 행은 한 역으로 묶고 좌표는 평균 (환승역).
  같은 이름이 서로 떨어진 곳에 있으면 노선으로 구분한다 (예: '신촌역(2호선)', '신촌역(경의중앙선)').
- 서울 밖 역(인천·경기)은 서울관광재단 식당 데이터가 반경 500m 안에 한 곳도 없으면 제외한다
  (식당 데이터가 서울 전역만 다루므로 '추천할 수 있는 역'만 남긴다).
- 강남역·역삼역은 기존 서비스 기준 좌표를 그대로 쓴다 (이미 저장된 계획·문서와 같은 기준).
- 요청 처리 중에는 저장된 목록만 읽는다 (없으면 강남역·역삼역). 목록은 서버 시작 시 백그라운드와 캐시 구축 스크립트,
  모르는 역 요청 때 받는다. 받지 못하면 10분 뒤 다시 시도한다.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from app.clients.seoul_opendata import SeoulOpenDataClient
from app.core.geo import haversine_m
from app.datasets.cache import JsonCache

logger = logging.getLogger(__name__)

SERVICE_STATION_MASTER = "subwayStationMaster"
BUILTIN: dict[str, tuple[float, float]] = {
    "강남역": (37.497952, 127.027619),
    "역삼역": (37.500622, 127.036456),
}
MERGE_DISTANCE_M = 500
SEOUL_CHECK_RADIUS_M = 500
RETRY_AFTER_SEC = 600

# 역 이름 대신 흔히 쓰는 말 → 역 이름 (역 목록에 있을 때만 적용)
ALIASES = {
    "홍대": "홍대입구역", "건대": "건대입구역", "서울대": "서울대입구역", "고터": "고속터미널역",
    "동대문운동장": "동대문역사문화공원역", "DDP": "동대문역사문화공원역",
}
# 이름만 말해도(역 없이) 역으로 보지 않는 흔한 낱말
NOT_BARE = {"서울", "방학", "개봉", "신사", "구일", "중앙", "시청", "대림", "내방", "마천", "상계", "중계", "신림"}
# 이름만 말했을 때 역으로 인정하는 뒷말 (예: '신촌에서', '성수 근처')
BARE_SUFFIX = r"(?=\s*(?:역|에서|근처|주변|부근|쪽|앞|일대|인근))"


@dataclass(frozen=True)
class Station:
    name: str  # 표시 이름 (예: '강남역', '서울역', '신촌역(2호선)')
    base: str  # 역 없이 부르는 이름 (예: '강남', '서울', '신촌')
    lines: tuple[str, ...]
    latitude: float
    longitude: float

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "base": self.base, "lines": list(self.lines), "latitude": self.latitude, "longitude": self.longitude}


def _display(base: str) -> str:
    return base if base.endswith("역") else f"{base}역"


def _base(name: str) -> str:
    """'잠실(송파구청)' → '잠실', '서울역' → '서울', '강남' → '강남'."""
    n = re.sub(r"\s*\(.*?\)\s*", "", name).strip()
    return n[:-1] if n.endswith("역") and len(n) > 2 else n


def build_stations(rows: list[dict[str, Any]], keep=lambda st: True) -> list[Station]:
    """역사마스터 행 → 역 목록. 이름(괄호·'역' 제외)이 같고 500m 안인 행을 한 역으로 묶는다.
    keep 으로 거른 뒤에도 같은 이름이 둘 이상 남을 때만 노선으로 구분한다."""
    by_base: dict[str, list[tuple[float, float, str]]] = {}
    for r in rows:
        base = _base(str(r.get("BLDN_NM") or "").strip())
        try:
            lat, lng = float(r.get("LAT")), float(r.get("LOT"))
        except (TypeError, ValueError):
            continue
        if base:
            by_base.setdefault(base, []).append((lat, lng, str(r.get("ROUTE") or "").strip()))
    out: list[Station] = []
    for base, pts in by_base.items():
        clusters: list[list[tuple[float, float, str]]] = []
        for p in pts:
            for c in clusters:
                if any(haversine_m(p[0], p[1], q[0], q[1]) <= MERGE_DISTANCE_M for q in c):
                    c.append(p)
                    break
            else:
                clusters.append([p])
        found = []
        for c in clusters:
            lines = tuple(dict.fromkeys(x[2] for x in c if x[2]))
            st = Station(_display(base), base, lines, sum(x[0] for x in c) / len(c), sum(x[1] for x in c) / len(c))
            if keep(st):
                found.append(st)
        if len(found) > 1:
            found = [Station(f"{st.name}({st.lines[0] if st.lines else i + 1})", st.base, st.lines, st.latitude, st.longitude)
                     for i, st in enumerate(found)]
        out.extend(found)
    return out


class StationDirectory:
    CACHE_NAME = "seoul_stations"

    def __init__(self, client: SeoulOpenDataClient | None, cache: JsonCache | None, restaurants=None):
        self.client = client
        self.cache = cache
        self.restaurants = restaurants  # RedtableRestaurantDataset (서울 여부 판정)
        self._failed_at: float | None = None
        self._memo: tuple[Any, list[Station]] | None = None

    # ------------------------------------------------------------ 목록
    def _build(self):
        page = self.client.fetch_all(SERVICE_STATION_MASTER)

        def in_service(st: Station) -> bool:
            return self.restaurants is None or self.restaurants.count_near(st.latitude, st.longitude, SEOUL_CHECK_RADIUS_M) > 0

        stations = build_stations(page.rows, in_service)
        kept = [st.to_dict() for st in stations if st.base not in ("강남", "역삼")]  # 두 역은 기존 기준 좌표로 따로 추가
        return kept, {"source": "서울시 역사마스터 정보", "source_rows": len(page.rows), "stations": len(kept) + len(BUILTIN)}

    def _builtin(self) -> list[Station]:
        return [Station(n, _base(n), ("2호선",), lat, lng) for n, (lat, lng) in BUILTIN.items()]

    def stations(self) -> list[Station]:
        """저장된 역 목록 (요청 처리 중에는 외부 호출을 하지 않는다). 없으면 강남역·역삼역."""
        payload = self.cache.load(self.CACHE_NAME) if self.cache is not None else None
        if payload is None:
            return self._builtin()
        if self._memo and self._memo[0] is payload:
            return self._memo[1]
        items = self._builtin() + [Station(d["name"], d["base"], tuple(d["lines"]), d["latitude"], d["longitude"])
                                   for d in payload["data"]]
        self._memo = (payload, items)
        return items

    def refresh(self) -> bool:
        """역 목록을 (없거나 만료면) 받아 저장한다. 서버 시작 시 백그라운드·캐시 구축 스크립트·모르는 역 요청 때 호출."""
        if self.client is None or self.cache is None:
            return False
        if self._failed_at and time.monotonic() - self._failed_at < RETRY_AFTER_SEC:
            return False
        try:
            self.cache.get_or_build(self.CACHE_NAME, self._build)
            return True
        except Exception:  # noqa: BLE001 - 역 목록을 못 받아도 기본 두 역으로 서비스는 계속
            logger.warning("역 목록을 받지 못해 강남역·역삼역만 사용합니다", exc_info=True)
            self._failed_at = time.monotonic()
            return False

    def names(self) -> list[str]:
        return [s.name for s in self.stations()]

    def get(self, name: str | None, *, refresh: bool = False) -> Station | None:
        """이름(또는 '역' 없는 이름)으로 역을 찾는다. refresh=True 면 못 찾았을 때 역 목록을 받아 한 번 더 찾는다."""
        if not name:
            return None
        hit = self._get(name.strip())
        if hit is None and refresh and self.refresh():
            hit = self._get(name.strip())
        return hit

    def _get(self, name: str) -> Station | None:
        stations = self.stations()
        for s in stations:
            if s.name == name:
                return s
        hits = [s for s in stations if s.base == _base(_display(name))]
        return hits[0] if hits else None

    # ------------------------------------------------------------ 발화에서 역 찾기
    def find_in_text(self, text: str) -> Station | None:
        """발화에서 역을 찾는다. 'OO역' 이 먼저, 그다음 별칭, 그다음 'OO에서/근처' 같은 이름만 쓴 표현. 긴 이름 우선."""
        stations = sorted(self.stations(), key=lambda s: -len(s.base))
        for s in stations:  # '신논현역' 이 '논현역' 보다 먼저 맞도록 앞 글자 경계 확인
            if re.search(rf"(?<![가-힣]){re.escape(s.base)}\s*역", text):
                return s
        for word, target in ALIASES.items():
            if re.search(rf"(?<![가-힣A-Za-z]){re.escape(word)}", text):
                hit = self.get(target)
                if hit:
                    return hit
        for s in stations:
            if s.base in ("강남", "역삼") and s.base in text:
                return s  # 기존 동작 유지: '강남', '역삼' 은 이름만 있어도 인정
            if len(s.base) >= 2 and s.base not in NOT_BARE and re.search(rf"(?<![가-힣]){re.escape(s.base)}{BARE_SUFFIX}", text):
                return s
        return None

    def nearest_other(self, name: str, max_m: float = 2000) -> Station | None:
        here = self.get(name)
        if here is None:
            return None
        best = None
        for s in self.stations():
            if s.name == here.name:
                continue
            d = haversine_m(here.latitude, here.longitude, s.latitude, s.longitude)
            if d <= max_m and (best is None or d < best[0]):
                best = (d, s)
        return best[1] if best else None
