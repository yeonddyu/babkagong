from __future__ import annotations

import pytest

from app.core.config import Settings


@pytest.fixture
def make_settings(tmp_path):
    """API 키를 원하는 대로 지정한 Settings 를 만든다. 실제 .env 는 읽지 않는다."""

    def _make(redtable="test-redtable", seoul="test-seoul", kakao="test-kakao", timeout=3.0):
        return Settings(
            redtable_api_key=redtable,
            seoul_openapi_key=seoul,
            kakao_rest_api_key=kakao,
            http_timeout_sec=timeout,
            cache_dir=tmp_path / "cache",
            cache_ttl_hours=168,
        )

    return _make
