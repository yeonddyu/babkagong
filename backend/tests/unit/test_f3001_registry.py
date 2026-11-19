"""F3001 Tool 명세 정의 및 등록 - Mock 단위 테스트."""
from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from app.core.errors import ErrorCode, ExternalAPIError
from app.tools.common import ToolError, ToolKind, ToolResult, ToolSpec
from app.tools.registry import ToolRegistry


class EchoIn(BaseModel):
    text: str = Field(min_length=1)
    repeat: int = Field(default=1, ge=1, le=3)


class EchoOut(BaseModel):
    text: str


def _echo(p: EchoIn) -> EchoOut:
    return EchoOut(text=p.text * p.repeat)


def _spec(name="echo_text", func=_echo, kind=ToolKind.LOCAL_SERVER_API):
    return ToolSpec(
        name=name,
        description="테스트용 Tool. 입력 문자열을 그대로 돌려줘야 할 때 사용한다.",
        kind=kind,
        input_model=EchoIn,
        output_model=EchoOut,
        error_codes=[ErrorCode.INVALID_INPUT],
        func=func,
    )


def _assert_failure(result, code):
    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == code.value
    assert result["error"]["message"]


def test_error_codes_defined():
    assert {c.value for c in ErrorCode} >= {
        "MISSING_API_KEY", "INVALID_INPUT", "NO_RESULT", "TIMEOUT", "API_ERROR", "DETAIL_NOT_AVAILABLE",
    }


def test_tool_kinds_distinguished():
    assert ToolKind.EXTERNAL_API.value == "external_api"
    assert ToolKind.LOCAL_SERVER_API.value == "local_server_api"


def test_tool_result_shape_enforced():
    ok = ToolResult.success({"a": 1}).model_dump(mode="json")
    assert ok == {"ok": True, "data": {"a": 1}, "error": None}
    fail = ToolResult.failure(ErrorCode.NO_RESULT, "없음").model_dump(mode="json")
    assert fail == {"ok": False, "data": None, "error": {"code": "NO_RESULT", "message": "없음"}}
    with pytest.raises(ValueError):
        ToolResult(ok=True, data=None, error=None)
    with pytest.raises(ValueError):
        ToolResult(ok=False, data={"x": 1}, error=None)


def test_register_and_describe():
    reg = ToolRegistry()
    reg.register(_spec())
    reg.register(_spec(name="echo_external", kind=ToolKind.EXTERNAL_API))
    assert reg.names() == ["echo_text", "echo_external"]
    desc = {d["name"]: d for d in reg.describe()}
    assert desc["echo_text"]["kind"] == "local_server_api"
    assert desc["echo_external"]["kind"] == "external_api"
    assert desc["echo_text"]["input_schema"]["required"] == ["text"]
    assert "text" in desc["echo_text"]["output_schema"]["properties"]


def test_duplicate_name_rejected():
    reg = ToolRegistry()
    reg.register(_spec())
    with pytest.raises(ValueError):
        reg.register(_spec())


def test_invalid_tool_name_rejected():
    with pytest.raises(ValueError):
        _spec(name="Bad Name")


def test_invoke_success():
    reg = ToolRegistry()
    reg.register(_spec())
    assert reg.invoke("echo_text", {"text": "밥", "repeat": 2}) == {"ok": True, "data": {"text": "밥밥"}, "error": None}


def test_invoke_missing_required_input():
    reg = ToolRegistry()
    reg.register(_spec())
    _assert_failure(reg.invoke("echo_text", {}), ErrorCode.INVALID_INPUT)


def test_invoke_unknown_tool():
    _assert_failure(ToolRegistry().invoke("nope", {}), ErrorCode.INVALID_INPUT)


@pytest.mark.parametrize(
    "exc, code",
    [
        (ToolError(ErrorCode.NO_RESULT, "결과 없음"), ErrorCode.NO_RESULT),
        (ExternalAPIError(ErrorCode.TIMEOUT, "시간 초과"), ErrorCode.TIMEOUT),
        (ExternalAPIError(ErrorCode.MISSING_API_KEY, "키 없음"), ErrorCode.MISSING_API_KEY),
        (RuntimeError("boom secret=abc"), ErrorCode.API_ERROR),
    ],
)
def test_invoke_never_raises(exc, code):
    def _raise(_):
        raise exc

    reg = ToolRegistry()
    reg.register(_spec(func=_raise))
    result = reg.invoke("echo_text", {"text": "x"})
    _assert_failure(result, code)
    assert "secret=abc" not in result["error"]["message"]  # 예외 상세를 그대로 노출하지 않음


def test_invoke_bad_output_becomes_api_error():
    reg = ToolRegistry()
    reg.register(_spec(func=lambda p: {"wrong": 1}))
    _assert_failure(reg.invoke("echo_text", {"text": "x"}), ErrorCode.API_ERROR)


def test_langchain_conversion():
    reg = ToolRegistry()
    reg.register(_spec())
    (tool,) = reg.as_langchain_tools()
    assert tool.name == "echo_text"
    assert "사용한다" in tool.description
    assert set(tool.args) == {"text", "repeat"}
    assert tool.invoke({"text": "a"}) == {"ok": True, "data": {"text": "a"}, "error": None}


def test_default_registry_builds(make_settings):
    from app.tools.catalog import build_default_registry

    reg = build_default_registry(make_settings())
    for spec in reg.specs():
        assert spec.description and spec.input_model and spec.output_model
