"""공통 오류 코드와 외부 API 예외.

Tool 계층과 외부 API Client 계층이 같은 오류 코드를 공유한다.
Client 는 ExternalAPIError 를 던지고, Tool 래퍼가 이를 공통 실패 응답으로 바꾼다.
"""
from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    MISSING_API_KEY = "MISSING_API_KEY"  # 환경변수에 API 키가 없음 (재시도해도 결과 동일)
    INVALID_INPUT = "INVALID_INPUT"  # 입력 스키마 검증 실패
    NO_RESULT = "NO_RESULT"  # 정상 호출했지만 조건에 맞는 결과가 없음
    TIMEOUT = "TIMEOUT"  # 외부 API 응답 시간 초과
    API_ERROR = "API_ERROR"  # 외부 API 인증 실패, HTTP 오류, 응답 형식 오류 등
    DETAIL_NOT_AVAILABLE = "DETAIL_NOT_AVAILABLE"  # 해당 출처는 상세정보를 제공하지 않음


class ExternalAPIError(Exception):
    """외부 API Client 가 던지는 예외. message 에는 비밀키를 넣지 않는다."""

    def __init__(self, code: ErrorCode, message: str, *, provider: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.provider = provider

    def __repr__(self) -> str:  # pragma: no cover - 디버깅용
        return f"ExternalAPIError({self.code.value}, {self.message!r}, provider={self.provider!r})"
