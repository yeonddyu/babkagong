from __future__ import annotations

import pytest

from app.core.config import load_settings


@pytest.fixture(scope="session")
def live_settings():
    return load_settings()


def require_key(value: str | None, env_name: str) -> str:
    if not value:
        pytest.skip(f"BLOCKED: {env_name} 미설정 - 실제 API 통합 테스트를 실행하지 않음")
    return value
