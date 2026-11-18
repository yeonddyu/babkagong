"""F3002 실제 API 통합 테스트. 실행: pytest -m integration -rs"""
from __future__ import annotations

import pytest

from app.clients.redtable import ENDPOINT_RESTAURANT, RedtableClient
from app.clients.seoul_opendata import SERVICE_GANGNAM_GENERAL_RESTAURANT, SeoulOpenDataClient
from app.core.errors import ErrorCode, ExternalAPIError
from app.datasets.restaurants import normalize_gangnam_license, normalize_redtable_restaurant
from app.tools.catalog import build_default_registry
from tests.integration.conftest import require_key

pytestmark = pytest.mark.integration


def test_seoul_opendata_public_sample_key():
    """공개 sample 키(최대 5건)로 실제 응답 구조와 정규화를 확인한다. 개인 키 없이 실행 가능."""
    page = SeoulOpenDataClient("sample", timeout=15).fetch_rows(SERVICE_GANGNAM_GENERAL_RESTAURANT, 1, 5)
    assert page.total_count > 1000
    assert len(page.rows) == 5
    records = [normalize_gangnam_license(r) for r in page.rows]
    assert all(r and r.source_id and r.name for r in records)
    assert all("강남구" in (r.road_address or r.jibun_address or "") for r in records)
    with_coord = [r for r in records if r.latitude is not None]
    assert with_coord, "좌표가 있는 행이 하나도 없음"
    for r in with_coord:  # 강남구 대략 범위
        assert 37.45 < r.latitude < 37.54 and 127.01 < r.longitude < 127.12


def test_seoul_opendata_sample_key_limit_is_reported():
    with pytest.raises(ExternalAPIError) as exc:
        SeoulOpenDataClient("sample", timeout=15).fetch_rows(SERVICE_GANGNAM_GENERAL_RESTAURANT, 1, 6)
    assert exc.value.code == ErrorCode.API_ERROR


def test_seoul_opendata_personal_key(live_settings):
    key = require_key(live_settings.seoul_openapi_key, "SEOUL_OPENAPI_KEY")
    page = SeoulOpenDataClient(key, timeout=15).fetch_rows(SERVICE_GANGNAM_GENERAL_RESTAURANT, 1, 100)
    assert len(page.rows) == 100


def test_redtable_restaurant_first_page(live_settings):
    key = require_key(live_settings.redtable_api_key, "REDTABLE_API_KEY")
    page = RedtableClient(key, timeout=20).fetch_page(ENDPOINT_RESTAURANT, 1)
    assert page.total_count > 0 and page.rows
    rec = normalize_redtable_restaurant(page.rows[0])
    assert rec and rec.source_id and rec.name


def test_redtable_invalid_key_rejected():
    """잘못된 키로 실제 호출 시 인증 오류가 API_ERROR 로 변환되는지 확인 (키 불필요)."""
    with pytest.raises(ExternalAPIError) as exc:
        RedtableClient("invalid-key-for-test", timeout=15).fetch_page(ENDPOINT_RESTAURANT, 1)
    assert exc.value.code == ErrorCode.API_ERROR
    assert "invalid-key-for-test" not in exc.value.message


def test_search_restaurant_candidates_live(live_settings):
    require_key(live_settings.redtable_api_key, "REDTABLE_API_KEY")
    require_key(live_settings.seoul_openapi_key, "SEOUL_OPENAPI_KEY")
    result = build_default_registry(live_settings).invoke("search_restaurant_candidates", {"area": "역삼역", "max_results": 5})
    assert result["ok"] is True, result["error"]
    assert result["data"]["candidates"]
