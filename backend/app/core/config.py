"""환경변수 기반 설정. API 키는 .env 또는 OS 환경변수에서만 읽는다 (NF3001).

키 값은 로그·응답에 출력하지 않는다. 존재 여부만 key_status() 로 확인한다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
PROJECT_ROOT = BACKEND_ROOT  # 하위 호환

# 환경변수 이름 → 허용 별칭 (앞의 이름이 표준, 실제 .env 에 쓰인 이름)
ENV_REDTABLE_KEY = "REDTABLE_API_KEY"  # 서울관광재단 음식관광 API (레드테이블) 토큰
ENV_SEOUL_KEY = "SEOUL_OPENAPI_KEY"  # 서울 열린데이터광장 인증키
ENV_KAKAO_KEY = "KAKAO_REST_API_KEY"  # 카카오 로컬 REST API 키
ENV_KMA_KEY = "KMA_API_KEY"  # 기상청 단기예보 (공공데이터포털 serviceKey, 인코딩된 값)
ENV_OPENAI_KEY = "OPENAI_API_KEY"
ENV_GMS_KEY = "GMS_API_KEY"  # SSAFY GMS — 현재는 존재 여부만 확인, 모델 연동 안 함

ALIASES: dict[str, tuple[str, ...]] = {
    ENV_REDTABLE_KEY: ("SEOUL_FOOD_API_TOKEN",),
    ENV_SEOUL_KEY: ("SEOUL_OPEN_API_KEY",),
}


@dataclass(frozen=True)
class Settings:
    redtable_api_key: str | None
    seoul_openapi_key: str | None
    kakao_rest_api_key: str | None
    http_timeout_sec: float
    cache_dir: Path
    cache_ttl_hours: float
    kma_api_key: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    gms_api_key: str | None = None
    ai_provider: str = "openai"
    max_replans: int = 3
    database_url: str = ""

    def key_status(self) -> dict[str, bool]:
        """API 키 존재 여부만 반환한다 (값은 노출하지 않음)."""
        return {
            ENV_REDTABLE_KEY: bool(self.redtable_api_key),
            ENV_SEOUL_KEY: bool(self.seoul_openapi_key),
            ENV_KAKAO_KEY: bool(self.kakao_rest_api_key),
            ENV_KMA_KEY: bool(self.kma_api_key),
            ENV_OPENAI_KEY: bool(self.openai_api_key),
            ENV_GMS_KEY: bool(self.gms_api_key),
        }


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _get(name: str) -> str | None:
    for candidate in (name, *ALIASES.get(name, ())):
        value = _clean(os.getenv(candidate))
        if value:
            return value
    return None


def load_settings(*, load_env_file: bool = True) -> Settings:
    if load_env_file:
        load_dotenv(REPO_ROOT / ".env", override=False)
        load_dotenv(BACKEND_ROOT / ".env", override=False)
    cache_dir = Path(os.getenv("BABKAGONG_CACHE_DIR") or BACKEND_ROOT / "data" / "cache")
    db_url = os.getenv("DATABASE_URL") or f"sqlite:///{BACKEND_ROOT / 'data' / 'babkagong.db'}"
    return Settings(
        redtable_api_key=_get(ENV_REDTABLE_KEY),
        seoul_openapi_key=_get(ENV_SEOUL_KEY),
        kakao_rest_api_key=_get(ENV_KAKAO_KEY),
        http_timeout_sec=float(os.getenv("HTTP_TIMEOUT_SEC") or "10"),
        cache_dir=cache_dir,
        cache_ttl_hours=float(os.getenv("CACHE_TTL_HOURS") or "168"),
        kma_api_key=_get(ENV_KMA_KEY),
        openai_api_key=_get(ENV_OPENAI_KEY),
        openai_model=os.getenv("OPENAI_MODEL") or "gpt-4o-mini",
        gms_api_key=_get(ENV_GMS_KEY),
        # GMS 는 아직 연동하지 않는다. AI_PROVIDER 값과 무관하게 llm_provider 가 OpenAI 만 반환한다.
        ai_provider=(os.getenv("AI_PROVIDER") or "openai").strip().lower(),
        max_replans=int(os.getenv("MAX_REPLANS") or "3"),
        database_url=db_url,
    )
