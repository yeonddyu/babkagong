"""F3004 실제 API 통합 테스트. 실행: pytest -m integration -rs"""
from __future__ import annotations

import pytest

from app.clients.kakao_local import CATEGORY_CAFE, KakaoLocalClient
from app.core.errors import ErrorCode, ExternalAPIError
from app.core.geo import STATIONS
from app.tools.catalog import build_default_registry
from tests.integration.conftest import require_key

pytestmark = pytest.mark.integration


def test_kakao_invalid_key_rejected():
    """잘못된 키로 실제 호출 시 401 이 API_ERROR 로 변환되는지 확인 (키 불필요)."""
    lat, lng = STATIONS["강남역"]
    with pytest.raises(ExternalAPIError) as exc:
        KakaoLocalClient("invalid-key-for-test", timeout=10).search_category(CATEGORY_CAFE, lat=lat, lng=lng, radius_m=300)
    assert exc.value.code == ErrorCode.API_ERROR
    assert "invalid-key-for-test" not in exc.value.message


def _require_kakao_enabled(settings):
    """키가 있어도 앱에서 카카오맵이 비활성(403)이면 BLOCKED 로 skip 한다."""
    key = require_key(settings.kakao_rest_api_key, "KAKAO_REST_API_KEY")
    lat, lng = STATIONS["강남역"]
    try:
        KakaoLocalClient(key, timeout=10).search_category(CATEGORY_CAFE, lat=lat, lng=lng, radius_m=100, size=1)
    except ExternalAPIError as exc:
        if "403" in exc.message:
            pytest.skip("BLOCKED: 카카오 앱에서 카카오맵(OPEN_MAP_AND_LOCAL) 서비스가 비활성 (HTTP 403)")
        raise


def test_search_nearby_cafes_live(live_settings):
    _require_kakao_enabled(live_settings)
    lat, lng = STATIONS["역삼역"]
    result = build_default_registry(live_settings).invoke(
        "search_nearby_cafes", {"latitude": lat, "longitude": lng, "radius_m": 300, "max_results": 5}
    )
    assert result["ok"], result["error"]
    assert result["data"]["source_status"][0] == {"source": "kakao_local_category_CE7", "ok": True,
                                                  "returned": len(result["data"]["cafes"]), "error_code": None, "message": None}
    for cafe in result["data"]["cafes"]:
        assert cafe["address"] or cafe["road_address"]
        assert cafe["place_url"].startswith("http")
        assert cafe["distance_m"] is None or cafe["distance_m"] <= 300
        assert cafe["opening_hours"] is None and cafe["wifi"] is None


def test_search_nearby_cafes_live_no_result(live_settings):
    _require_kakao_enabled(live_settings)
    # 서해 바다 위 좌표, 반경 1m → 결과 없음
    result = build_default_registry(live_settings).invoke(
        "search_nearby_cafes", {"latitude": 37.0, "longitude": 125.0, "radius_m": 1}
    )
    assert result["ok"] is False and result["error"]["code"] == "NO_RESULT"


def test_rest_food_fallback_live(live_settings):
    """카카오가 실패하는 상태에서 강남구 휴게음식점 인허가(실제 API)로 보조 검색되는지 확인."""
    from dataclasses import replace

    require_key(live_settings.seoul_openapi_key, "SEOUL_OPENAPI_KEY")
    settings = replace(live_settings, kakao_rest_api_key="invalid-key-for-fallback-test")
    lat, lng = STATIONS["역삼역"]
    result = build_default_registry(settings).invoke(
        "search_nearby_cafes", {"latitude": lat, "longitude": lng, "radius_m": 300, "max_results": 5}
    )
    assert result["ok"], result["error"]
    data = result["data"]
    assert data["source_status"][0]["ok"] is False  # 카카오 실패
    assert data["cafes"] and all(c["source"] == "gangnam_rest_food_license" for c in data["cafes"])
    for cafe in data["cafes"]:
        assert cafe["distance_m"] <= 300 and cafe["place_url"] is None
        assert cafe["road_address"] or cafe["address"]
