"""API 요청·응답 모델 (F3017). 오류 응답에는 내부 예외·키를 넣지 않는다 (NF3002)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.storage.plans import ConflictOut, PlanOut


class ErrorBody(BaseModel):
    code: Literal["INVALID_INPUT", "NOT_FOUND", "INTERNAL_ERROR"]
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorBody


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500, description="사용자 발화")
    session_id: str | None = Field(default=None, max_length=64, description="이어서 대화할 세션 ID (없으면 새로 발급)")
    area: Literal["강남역", "역삼역"] | None = Field(default=None, description="화면에서 선택한 지역 (발화에 지역이 없을 때 사용)")


class ChatEvent(BaseModel):
    session_id: str
    run_id: str
    seq: int
    type: str
    stage: str | None
    payload: dict[str, Any]
    timestamp: str


class ChatResponse(BaseModel):
    session_id: str
    run_id: str
    intent: str
    intent_reason: str
    decided_by: Literal["llm", "rule"]
    message: str = Field(description="사용자에게 보여줄 응답 문장")
    message_by: Literal["template", "llm"]
    summary: str | None = Field(default=None, description="대화창용 짧은 요약 (코드 생성, 추천이 있을 때만)")
    conditions: dict[str, Any] = Field(description="기준·선호·제약 조건, missing, changed")
    plan: dict[str, Any] | None = Field(description="Tool 호출 계획")
    clarify: bool
    weather: dict[str, Any] | None
    weather_policy: list[str]
    recommendations: list[dict[str, Any]] = Field(description="추천 식당 + 주변 카페 + 판단 근거")
    excluded: list[dict[str, Any]] = Field(description="제외 후보와 사유")
    criteria: list[str] = Field(description="판단 기준")
    evidence: list[dict[str, Any]] = Field(description="근거 Tool 호출 이력")
    replans: list[dict[str, Any]]
    stop_reason: str | None
    suggestions: list[str]
    notices: list[str] = Field(description="Tool 실패·API 키 누락 안내 (사용자용 문장)")
    disclaimer: str | None
    query_basis: dict[str, Any] | None
    saved_plan: dict[str, Any] | None
    plan_conflicts: list[dict[str, Any]]
    more: bool = Field(default=False, description="'더 보기' 요청으로 앞서 보여 준 곳을 제외한 결과인지")
    events: list[ChatEvent] = Field(description="이번 실행의 이벤트 (실행 순서)")
    elapsed_ms: int


class HealthResponse(BaseModel):
    status: Literal["ok"]
    api_keys: dict[str, bool] = Field(description="환경변수 존재 여부만 (값 미노출)")
    llm: dict[str, Any]
    tools: list[str]
    max_replans: int


class PlanSaveResponse(BaseModel):
    plan: PlanOut
    conflicts: list[ConflictOut] = Field(description="같은 날짜에 시간이 겹치는 다른 계획 (저장은 완료)")


class PlanListResponse(BaseModel):
    plans: list[PlanOut]


class LogSessionSummary(BaseModel):
    session_id: str
    event_count: int
    run_count: int
    first_at: str
    last_at: str
    first_message: str | None


class LogListResponse(BaseModel):
    sessions: list[LogSessionSummary]


class LogEntry(BaseModel):
    id: int
    session_id: str
    run_id: str
    seq: int
    type: str
    stage: str | None
    payload: dict[str, Any]
    timestamp: str


class LogDetailResponse(BaseModel):
    session_id: str
    events: list[LogEntry]


class DeleteResponse(BaseModel):
    deleted: bool
    count: int = 1
