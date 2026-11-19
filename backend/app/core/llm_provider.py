"""LLM 생성 공통 모듈.

기본 제공자는 SSAFY GMS(OpenAI 호환 프록시)다. ChatOpenAI 에 GMS 접속 주소와 GMS_API_KEY 를 넣어 쓴다.
AI_PROVIDER=openai 이면 OpenAI 를 직접 호출한다. 키가 없으면 None 을 돌려주고 Agent 는 규칙 기반으로 동작한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from app.core.config import DEFAULT_LLM_MODEL, Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMStatus:
    available: bool
    provider: str
    model: str | None
    reason: str | None = None  # 사용자 안내용 (키 값 미포함)


def _gms(settings: Settings) -> Any:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=settings.gms_model or DEFAULT_LLM_MODEL, api_key=settings.gms_api_key,
                      base_url=settings.gms_base_url, temperature=0, timeout=30, max_retries=1)


def _openai(settings: Settings) -> Any:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0, timeout=30, max_retries=1)


_PROVIDERS: dict[str, Callable[[Settings], Any]] = {"gms": _gms, "openai": _openai}


def llm_status(settings: Settings) -> LLMStatus:
    provider = settings.ai_provider if settings.ai_provider in _PROVIDERS else "gms"
    if provider != settings.ai_provider:
        logger.info("AI_PROVIDER=%s 는 지원하지 않아 GMS 를 사용합니다.", settings.ai_provider)
    if provider == "gms":
        model = settings.gms_model or DEFAULT_LLM_MODEL
        if not settings.gms_api_key:
            return LLMStatus(False, "gms", model, "GMS_API_KEY 가 설정되지 않아 규칙 기반으로 처리합니다.")
        return LLMStatus(True, "gms", model)
    if not settings.openai_api_key:
        return LLMStatus(False, "openai", settings.openai_model, "OPENAI_API_KEY 가 설정되지 않아 규칙 기반으로 처리합니다.")
    return LLMStatus(True, "openai", settings.openai_model)


def create_llm(settings: Settings) -> Any | None:
    """사용 가능한 LLM 을 반환한다. 키가 없으면 None (호출하지 않음)."""
    status = llm_status(settings)
    if not status.available:
        return None
    return _PROVIDERS[status.provider](settings)
