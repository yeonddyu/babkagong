"""밥카공 FastAPI 앱 (F3017).

실행 (backend/ 에서): ../.venv/bin/uvicorn app.main:app --port 8000
문서: http://localhost:8000/docs
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agent.graph import MainAgent
from app.api.routes import router
from app.core.config import Settings, load_settings
from app.core.llm_provider import create_llm
from app.events.bus import EventBus
from app.events.logging_agent import LoggingAgent
from app.storage.db import init_db, make_engine, make_session_factory
from app.storage.logs import LogRepository
from app.storage.plans import PlanRepository
from app.storage.sessions import SqliteMemoryStore
from app.tools.catalog import build_default_registry
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class Deps:
    settings: Settings
    registry: ToolRegistry
    agent: MainAgent
    plans: PlanRepository
    logs: LogRepository
    bus: EventBus
    logging_agent: LoggingAgent


def build_deps(settings: Settings, *, registry: ToolRegistry | None = None, agent_kwargs: dict[str, Any] | None = None) -> Deps:
    engine = make_engine(settings.database_url)
    init_db(engine)
    sf = make_session_factory(engine)
    plans, logs = PlanRepository(sf), LogRepository(sf)
    bus = EventBus()
    logging_agent = LoggingAgent(logs).attach(bus)  # 로깅 서브 Agent 구독
    registry = registry or build_default_registry(settings)
    agent = MainAgent(registry, llm=create_llm(settings), max_replans=settings.max_replans,
                      memory=SqliteMemoryStore(sf), bus=bus, plan_repo=plans, **(agent_kwargs or {}))
    return Deps(settings, registry, agent, plans, logs, bus, logging_agent)


def _warm_up(deps: Deps) -> None:
    """서버 시작 시 백그라운드로 서울 전역 식당 데이터·역 목록을 준비한다 (첫 요청 지연 방지, 테스트에서는 생략)."""
    directory = getattr(deps.registry, "stations", None)
    if directory is None or "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("BABKAGONG_WARMUP", "1") == "0":
        return

    def run():
        ok = directory.refresh()
        logger.info("역 목록 준비 %s: %d곳", "완료" if ok else "실패(강남역·역삼역만 사용)", len(directory.stations()))

    threading.Thread(target=run, name="warm-up", daemon=True).start()


def create_app(settings: Settings | None = None, *, deps: Deps | None = None) -> FastAPI:
    app = FastAPI(
        title="밥카공 API",
        version="1.0.0",
        description="서울 지하철역 주변 식사 + 카공 카페 코스 추천 Agent. 대화, 계획 관리, 실행 로그 조회 API.",
    )
    app.state.deps = deps or build_deps(settings or load_settings())
    _warm_up(app.state.deps)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        msg = "; ".join(f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors())
        return JSONResponse(status_code=422, content={"detail": {"code": "INVALID_INPUT", "message": msg}})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {
            "code": "NOT_FOUND" if exc.status_code == 404 else "INVALID_INPUT", "message": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})

    @app.exception_handler(Exception)
    async def _internal(_: Request, exc: Exception):  # pragma: no cover - 마지막 방어선
        logger.exception("처리되지 않은 오류")
        return JSONResponse(status_code=500, content={"detail": {"code": "INTERNAL_ERROR",
                                                                  "message": "서버 내부 오류가 발생했어요."}})

    app.include_router(router)
    return app


def __getattr__(name: str):  # uvicorn app.main:app 실행 시점에만 실제 의존성 생성
    if name == "app":
        global app
        app = create_app()
        return app
    raise AttributeError(name)
