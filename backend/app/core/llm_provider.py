"""LLM 생성 공통 모듈.

현재는 OpenAI(ChatOpenAI)만 반환한다. SSAFY GMS 는 키만 등록된 상태이며 모델·접속 주소가
확정되면 _PROVIDERS 에 생성 함수를 추가한다. AI_PROVIDER=gms 여도 GMS 를 호출하지 않는다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMStatus:
    available: bool
    provider: str
    model: str | None
    reason: str | None = None  # 사용자 안내용 (키 값 미포함)


def _openai(settings: Settings) -> Any:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0, timeout=30, max_retries=1)


_PROVIDERS: dict[str, Callable[[Settings], Any]] = {"openai": _openai}


def llm_status(settings: Settings) -> LLMStatus:
    if settings.ai_provider not in ("", "openai"):
        logger.info("AI_PROVIDER=%s 는 아직 연동되지 않아 OpenAI 를 사용합니다.", settings.ai_provider)
    if not settings.openai_api_key:
        return LLMStatus(False, "openai", settings.openai_model, "OPENAI_API_KEY 가 설정되지 않아 규칙 기반으로 처리합니다.")
    return LLMStatus(True, "openai", settings.openai_model)


def create_llm(settings: Settings) -> Any | None:
    """사용 가능한 LLM 을 반환한다. 키가 없으면 None (호출하지 않음)."""
    status = llm_status(settings)
    if not status.available:
        return None
    return _PROVIDERS["openai"](settings)
