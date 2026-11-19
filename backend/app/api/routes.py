"""FastAPI 라우터: 대화(/api/chat), 계획(/api/plans), 실행 로그(/api/logs), 상태(/api/health)."""
from __future__ import annotations

import logging
import time
from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import ValidationError

from app.api.schemas import (
    ChatRequest, ChatResponse, DeleteResponse, ErrorResponse, HealthResponse, LogDetailResponse, LogListResponse,
    PlanListResponse, PlanSaveResponse,
)
from app.core.llm_provider import llm_status
from app.storage.plans import PlanCreate, PlanNotFound, PlanOut, PlanUpdate

logger = logging.getLogger(__name__)
ERRORS = {400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}

router = APIRouter(prefix="/api")


def _deps(request: Request):
    return request.app.state.deps


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


# ---------------------------------------------------------------- 상태
@router.get("/health", response_model=HealthResponse, tags=["status"], summary="서버 상태와 API 키 설정 여부")
def health(request: Request):
    d = _deps(request)
    st = llm_status(d.settings)
    return HealthResponse(status="ok", api_keys=d.settings.key_status(),
                          llm={"available": st.available, "provider": st.provider, "model": st.model, "note": st.reason},
                          tools=d.registry.names(), max_replans=d.settings.max_replans)


# ---------------------------------------------------------------- 대화
@router.post("/chat", response_model=ChatResponse, responses=ERRORS, tags=["chat"], summary="대화 요청 → Agent 실행")
def chat(req: ChatRequest, request: Request):
    d = _deps(request)
    started = time.perf_counter()
    try:
        result = d.agent.run(req.message, session_id=req.session_id, area_hint=req.area)
    except Exception:  # noqa: BLE001 - 내부 오류 상세는 노출하지 않음 (NF3002)
        logger.exception("Agent 실행 실패")
        raise _error(500, "INTERNAL_ERROR", "요청을 처리하는 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요.")
    body = result["response"]
    return ChatResponse(
        session_id=result["session_id"], run_id=result["run_id"], events=result["events"],
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        **{k: body[k] for k in ChatResponse.model_fields if k in body},
    )


# ---------------------------------------------------------------- 계획
@router.get("/plans", response_model=PlanListResponse, tags=["plans"], summary="계획 목록")
def list_plans(request: Request, plan_date: date | None = Query(default=None, alias="date")):
    return PlanListResponse(plans=_deps(request).plans.list(plan_date))


@router.post("/plans", response_model=PlanSaveResponse, status_code=201, responses=ERRORS, tags=["plans"],
             summary="계획 저장 (시간 겹침은 저장 후 conflicts 로 안내)")
def create_plan(data: PlanCreate, request: Request):
    plan, conflicts = _deps(request).plans.create(data)
    return PlanSaveResponse(plan=plan, conflicts=conflicts)


@router.get("/plans/{plan_id}", response_model=PlanOut, responses=ERRORS, tags=["plans"], summary="계획 상세")
def get_plan(plan_id: int, request: Request):
    try:
        return _deps(request).plans.get(plan_id)
    except PlanNotFound:
        raise _error(404, "NOT_FOUND", "계획을 찾을 수 없어요.")


@router.put("/plans/{plan_id}", response_model=PlanSaveResponse, responses=ERRORS, tags=["plans"], summary="계획 수정")
def update_plan(plan_id: int, data: PlanUpdate, request: Request):
    try:
        plan, conflicts = _deps(request).plans.update(plan_id, data)
    except PlanNotFound:
        raise _error(404, "NOT_FOUND", "계획을 찾을 수 없어요.")
    except ValidationError as exc:
        raise _error(422, "INVALID_INPUT", "; ".join(e["msg"] for e in exc.errors()))
    return PlanSaveResponse(plan=plan, conflicts=conflicts)


@router.delete("/plans/{plan_id}", response_model=DeleteResponse, responses=ERRORS, tags=["plans"], summary="계획 삭제")
def delete_plan(plan_id: int, request: Request):
    try:
        _deps(request).plans.delete(plan_id)
    except PlanNotFound:
        raise _error(404, "NOT_FOUND", "계획을 찾을 수 없어요.")
    return DeleteResponse(deleted=True)


# ---------------------------------------------------------------- 실행 로그 (수정 API 없음)
@router.get("/logs", response_model=LogListResponse, tags=["logs"], summary="세션별 실행 로그 목록")
def list_logs(request: Request):
    return LogListResponse(sessions=_deps(request).logs.list_sessions())


@router.get("/logs/{session_id}", response_model=LogDetailResponse, responses=ERRORS, tags=["logs"],
            summary="세션 실행 로그 상세 (실행 순서)")
def get_logs(session_id: str, request: Request):
    events = _deps(request).logs.get_session(session_id)
    if not events:
        raise _error(404, "NOT_FOUND", "해당 세션의 실행 로그가 없어요.")
    return LogDetailResponse(session_id=session_id, events=events)


@router.delete("/logs/{session_id}", response_model=DeleteResponse, responses=ERRORS, tags=["logs"], summary="세션 실행 로그 삭제")
def delete_logs(session_id: str, request: Request):
    count = _deps(request).logs.delete_session(session_id)
    if count == 0:
        raise _error(404, "NOT_FOUND", "해당 세션의 실행 로그가 없어요.")
    return DeleteResponse(deleted=True, count=count)
