"""모든 Tool 이 공유하는 결과 형식과 Tool 명세 타입 (F3001).

성공: {"ok": true,  "data": {...}, "error": null}
실패: {"ok": false, "data": null,  "error": {"code": "...", "message": "..."}}
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.errors import ErrorCode, ExternalAPIError


class ToolKind(str, Enum):
    EXTERNAL_API = "external_api"  # 외부 API Client 를 감싼 Tool
    LOCAL_SERVER_API = "local_server_api"  # 이 서비스 서버 기능을 감싼 Tool


class ToolErrorInfo(BaseModel):
    code: ErrorCode
    message: str


class ToolResult(BaseModel):
    """공통 응답 envelope."""

    model_config = ConfigDict(use_enum_values=True)

    ok: bool
    data: dict[str, Any] | None = None
    error: ToolErrorInfo | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> "ToolResult":
        if self.ok and (self.data is None or self.error is not None):
            raise ValueError("성공 응답은 data 가 있고 error 가 null 이어야 한다")
        if not self.ok and (self.data is not None or self.error is None):
            raise ValueError("실패 응답은 data 가 null 이고 error 가 있어야 한다")
        return self

    @classmethod
    def success(cls, data: BaseModel | dict[str, Any]) -> "ToolResult":
        payload = data.model_dump(mode="json") if isinstance(data, BaseModel) else data
        return cls(ok=True, data=payload, error=None)

    @classmethod
    def failure(cls, code: ErrorCode, message: str) -> "ToolResult":
        return cls(ok=False, data=None, error=ToolErrorInfo(code=code, message=message))


class ToolError(Exception):
    """Tool 구현부가 의도적으로 실패를 알릴 때 사용한다."""

    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    @classmethod
    def from_external(cls, exc: ExternalAPIError) -> "ToolError":
        return cls(exc.code, exc.message)


class ToolSpec(BaseModel):
    """Agent 에 노출되는 Tool 명세."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    description: str = Field(min_length=20)
    kind: ToolKind
    providers: list[str] = Field(default_factory=list, description="래핑한 외부 API 제공처")
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    error_codes: list[ErrorCode]
    func: Callable[[Any], BaseModel]

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "description": self.description,
            "providers": self.providers,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
            "error_codes": [c.value for c in self.error_codes],
        }
