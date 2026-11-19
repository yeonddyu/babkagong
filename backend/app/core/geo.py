"""서비스 지역 좌표와 거리·좌표계 변환 유틸."""
from __future__ import annotations

import math
from functools import lru_cache

# 서비스 지역 중심 좌표 (WGS84). 지하철역 위치 기준.
STATIONS: dict[str, tuple[float, float]] = {
    "강남역": (37.497952, 127.027619),
    "역삼역": (37.500622, 127.036456),
}

LOCALDATA_CRS = "EPSG:5174"  # 지방행정인허가(LOCALDATA) X/Y 좌표계 (Bessel 중부원점 TM)


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def _tm_transformer():
    from pyproj import Transformer

    return Transformer.from_crs(LOCALDATA_CRS, "EPSG:4326", always_xy=True)


def tm_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """LOCALDATA TM 좌표(X, Y)를 (위도, 경도)로 변환한다."""
    lng, lat = _tm_transformer().transform(x, y)
    return lat, lng


def to_float(value) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).strip()
        return float(text) if text else None
    except ValueError:
        return None


def within_any_station(lat: float, lng: float, radius_m: float) -> bool:
    return any(haversine_m(lat, lng, s_lat, s_lng) <= radius_m for s_lat, s_lng in STATIONS.values())
