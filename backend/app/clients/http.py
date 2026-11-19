"""외부 API 공통 HTTP 호출. 네트워크/HTTP 오류를 ErrorCode 로 변환한다."""
from __future__ import annotations

import json
from typing import Any, Protocol

import requests

from app.core.errors import ErrorCode, ExternalAPIError


class HTTPSession(Protocol):  # requests.Session 과 테스트용 가짜 세션이 따르는 인터페이스
    def get(self, url: str, *, params: Any = None, headers: Any = None, timeout: float | None = None) -> Any: ...


def http_get(
    session: HTTPSession,
    url: str,
    *,
    provider: str,
    timeout: float,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    """GET 호출 후 (status_code, text) 반환. 네트워크 계층 오류만 예외로 바꾼다.

    URL·헤더에 비밀키가 들어갈 수 있으므로 예외 메시지에 URL 을 넣지 않는다.
    """
    try:
        resp = session.get(url, params=params, headers=headers, timeout=timeout)
    except requests.Timeout as exc:
        raise ExternalAPIError(ErrorCode.TIMEOUT, f"{provider} 응답 시간이 {timeout:g}초를 초과했습니다.", provider=provider) from exc
    except requests.RequestException as exc:
        raise ExternalAPIError(ErrorCode.API_ERROR, f"{provider} 연결에 실패했습니다.", provider=provider) from exc
    return resp.status_code, resp.text


def raise_for_http_status(status: int, provider: str) -> None:
    if status == 200:
        return
    if status in (401, 403):
        msg = f"{provider} 인증에 실패했습니다. API 키를 확인하세요. (HTTP {status})"
    elif status == 429:
        msg = f"{provider} 호출 한도를 초과했습니다. (HTTP 429)"
    elif status >= 500:
        msg = f"{provider} 서버 오류입니다. (HTTP {status})"
    else:
        msg = f"{provider} 요청이 실패했습니다. (HTTP {status})"
    raise ExternalAPIError(ErrorCode.API_ERROR, msg, provider=provider)


def parse_json(text: str, provider: str) -> Any:
    try:
        return json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ExternalAPIError(ErrorCode.API_ERROR, f"{provider} 응답이 JSON 형식이 아닙니다.", provider=provider) from exc
