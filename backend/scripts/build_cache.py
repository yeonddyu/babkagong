"""외부 API 데이터 캐시를 미리 구축하고 소요 시간을 기록한다.

레드테이블·서울 인허가 API 는 지역 필터가 없어 전체 페이지를 순회해야 하므로
서비스 시작 전에 한 번 실행해 두면 첫 요청의 응답 시간이 짧아진다 (NF3005).

실행 (backend/ 에서): ../.venv/bin/python -m scripts.build_cache
"""
from __future__ import annotations

import time

from app.clients.redtable import RedtableClient
from app.clients.seoul_opendata import SeoulOpenDataClient
from app.core.config import load_settings
from app.datasets.cache import JsonCache
from app.datasets.restaurants import GangnamLicenseDataset, RedtableDetailDataset, RedtableRestaurantDataset
from app.datasets.stations import StationDirectory


def _timed(label, fn):
    start = time.perf_counter()
    try:
        result = fn()
        print(f"[OK]   {label}: {time.perf_counter() - start:.1f}s {result}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {label}: {time.perf_counter() - start:.1f}s {type(exc).__name__}: {getattr(exc, 'message', '')}", flush=True)


def main() -> None:
    s = load_settings()
    cache = JsonCache(s.cache_dir, s.cache_ttl_hours)
    rt = RedtableClient(s.redtable_api_key, timeout=30)
    seoul = SeoulOpenDataClient(s.seoul_openapi_key, timeout=30)
    restaurants = RedtableRestaurantDataset(rt, cache)
    details = RedtableDetailDataset(rt, cache, restaurants)
    license_ = GangnamLicenseDataset(seoul, cache)
    rest_food = GangnamLicenseDataset.rest_food(seoul, cache)
    stations = StationDirectory(seoul, cache, restaurants)

    _timed("레드테이블 식당기본정보 (서울 전역, SQLite)", restaurants.ensure)
    _timed("레드테이블 식당운영정보 (서울 전역, SQLite)", details.ensure_operations)
    _timed("레드테이블 메뉴정보(한국어) (서울 전역, SQLite)", details.ensure_menus)
    _timed("강남구 일반음식점 인허가 (강남구 전체)", lambda: license_.load()[1] | {"rows": len(license_.load()[0])})
    _timed("강남구 휴게음식점 인허가 (강남구 전체)", lambda: rest_food.load()[1] | {"rows": len(rest_food.load()[0])})
    _timed("서울 지하철역 목록", lambda: {"refreshed": stations.refresh(), "stations": len(stations.stations())})


if __name__ == "__main__":
    main()
