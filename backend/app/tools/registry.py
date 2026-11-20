"""Tool 레지스트리 (F3001).

- Tool 등록/조회/명세 출력
- 입력 검증 → 실행 → 출력 검증 → 공통 envelope 변환을 한 곳에서 수행
- 어떤 예외도 밖으로 내보내지 않는다 (NF3003)
- LangChain StructuredTool 로 변환
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from pydantic import BaseModel, ValidationError

from app.core.errors import ErrorCode, ExternalAPIError
from app.tools.common import ToolError, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ())) or "(root)"
        parts.append(f"{loc}: {err.get('msg')}")
    return "입력값이 올바르지 않습니다 - " + "; ".join(parts)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self.stations = None  # StationDirectory (catalog 이 채움). 없으면 강남역·역삼역 기본 목록

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"이미 등록된 Tool 이름입니다: {spec.name}")
        self._tools[spec.name] = spec
        return spec

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def describe(self) -> list[dict[str, Any]]:
        return [spec.summary() for spec in self._tools.values()]

    def invoke(self, name: str, arguments: dict[str, Any] | BaseModel | None = None) -> dict[str, Any]:
        """Tool 을 실행하고 항상 공통 envelope(dict)을 반환한다."""
        spec = self._tools.get(name)
        if spec is None:
            return ToolResult.failure(ErrorCode.INVALID_INPUT, f"등록되지 않은 Tool 입니다: {name}").model_dump(mode="json")

        try:
            if isinstance(arguments, spec.input_model):
                params = arguments
            else:
                raw = arguments.model_dump() if isinstance(arguments, BaseModel) else (arguments or {})
                params = spec.input_model.model_validate(raw)
        except ValidationError as exc:
            return ToolResult.failure(ErrorCode.INVALID_INPUT, _format_validation_error(exc)).model_dump(mode="json")

        try:
            output = spec.func(params)
            validated = spec.output_model.model_validate(
                output.model_dump() if isinstance(output, BaseModel) else output
            )
            result = ToolResult.success(validated)
        except ToolError as exc:
            result = ToolResult.failure(exc.code, exc.message)
        except ExternalAPIError as exc:
            result = ToolResult.failure(exc.code, exc.message)
        except ValidationError:
            logger.exception("Tool %s 출력 스키마 검증 실패", name)
            result = ToolResult.failure(ErrorCode.API_ERROR, "외부 API 응답을 Tool 출력 형식으로 변환하지 못했습니다.")
        except Exception:  # noqa: BLE001 - 어떤 예외도 Agent 밖으로 전파하지 않는다
            logger.exception("Tool %s 실행 중 예상하지 못한 오류", name)
            result = ToolResult.failure(ErrorCode.API_ERROR, "Tool 실행 중 예상하지 못한 오류가 발생했습니다.")
        return result.model_dump(mode="json")

    def as_langchain_tools(self, names: Iterable[str] | None = None) -> list[Any]:
        """LangChain StructuredTool 목록으로 변환한다. 반환값은 항상 공통 envelope dict."""
        from langchain_core.tools import StructuredTool

        selected = list(names) if names is not None else self.names()
        tools = []
        for tool_name in selected:
            spec = self._tools[tool_name]

            def _run(_name: str = tool_name, **kwargs: Any) -> dict[str, Any]:
                return self.invoke(_name, kwargs)

            tools.append(
                StructuredTool.from_function(
                    func=_run,
                    name=spec.name,
                    description=spec.description,
                    args_schema=spec.input_model,
                    infer_schema=False,
                )
            )
        return tools
