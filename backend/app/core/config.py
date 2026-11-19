"""환경변수 기반 설정. API 키는 .env 또는 OS 환경변수에서만 읽는다 (NF3001)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 환경변수 이름 (값은 .env 에만 보관)
ENV_REDTABLE_KEY = "REDTABLE_API_KEY"  # 서울관광재단 음식관광 API (레드테이블) 토큰
ENV_SEOUL_KEY = "SEOUL_OPENAPI_KEY"  # 서울 열린데이터광장 인증키
ENV_KAKAO_KEY = "KAKAO_REST_API_KEY"  # 카카오 로컬 REST API 키


@dataclass(frozen=True)
class Settings:
    redtable_api_key: str | None
    seoul_openapi_key: str | None
    kakao_rest_api_key: str | None
    http_timeout_sec: float
    cache_dir: Path
    cache_ttl_hours: float


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def load_settings(*, load_env_file: bool = True) -> Settings:
    if load_env_file:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
    cache_dir = Path(os.getenv("BABKAGONG_CACHE_DIR") or PROJECT_ROOT / "data" / "cache")
    return Settings(
        redtable_api_key=_clean(os.getenv(ENV_REDTABLE_KEY)),
        seoul_openapi_key=_clean(os.getenv(ENV_SEOUL_KEY)),
        kakao_rest_api_key=_clean(os.getenv(ENV_KAKAO_KEY)),
        http_timeout_sec=float(os.getenv("HTTP_TIMEOUT_SEC", "10")),
        cache_dir=cache_dir,
        cache_ttl_hours=float(os.getenv("CACHE_TTL_HOURS", "168")),
    )
