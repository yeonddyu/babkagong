"""F3003 실제 API 통합 테스트. 실행: pytest -m integration -rs

주의: 메뉴정보·운영정보 API 는 식당 ID 필터가 없어 첫 실행 시 전체 페이지를 순회한다.
"""
from __future__ import annotations

import pytest

from app.clients.redtable import ENDPOINT_MENU_KOREAN, ENDPOINT_OPERATION, RedtableClient
from app.tools.catalog import build_default_registry
from tests.integration.conftest import require_key

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("endpoint, field", [(ENDPOINT_MENU_KOREAN, "MENU_NM"), (ENDPOINT_OPERATION, "RSTR_ID")])
def test_redtable_detail_endpoints_first_page(live_settings, endpoint, field):
    key = require_key(live_settings.redtable_api_key, "REDTABLE_API_KEY")
    page = RedtableClient(key, timeout=20).fetch_page(endpoint, 1)
    assert page.rows and field in page.rows[0]


def test_candidate_to_details_live(live_settings):
    require_key(live_settings.redtable_api_key, "REDTABLE_API_KEY")
    reg = build_default_registry(live_settings)
    cands = reg.invoke("search_restaurant_candidates", {"area": "역삼역", "max_results": 3})
    assert cands["ok"], cands["error"]
    first = cands["data"]["candidates"][0]
    detail = reg.invoke("get_restaurant_details", {"source": first["source"], "source_id": first["source_id"]})
    assert detail["ok"], detail["error"]
    assert detail["data"]["basic"]["name"] == first["name"]
