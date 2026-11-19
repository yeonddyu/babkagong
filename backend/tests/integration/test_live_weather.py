"""기상청 날씨 Tool 실제 API 통합 테스트."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.datasets.cache import now_kst
from app.tools.catalog import build_default_registry
from tests.integration.conftest import require_key

pytestmark = pytest.mark.integration


def test_weather_live_next_hour(live_settings):
    require_key(live_settings.kma_api_key, "KMA_API_KEY")
    result = build_default_registry(live_settings).invoke("get_weather_context", {"area": "강남역"})
    assert result["ok"], result["error"]
    d = result["data"]
    assert d["grid"] == {"nx": 61, "ny": 125}
    assert d["temperature_c"] is not None and d["precipitation_probability"] is not None
    assert d["base_datetime"] < d["forecast_datetime"]


def test_weather_live_tomorrow_noon(live_settings):
    require_key(live_settings.kma_api_key, "KMA_API_KEY")
    tomorrow = (now_kst() + timedelta(days=1)).date().isoformat()
    result = build_default_registry(live_settings).invoke(
        "get_weather_context", {"area": "역삼역", "visit_date": tomorrow, "visit_time": "12:00"})
    assert result["ok"], result["error"]
    assert result["data"]["forecast_datetime"].startswith(f"{tomorrow}T12:00")
