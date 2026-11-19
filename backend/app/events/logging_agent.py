"""F3013 로깅 서브 Agent.

EventBus 를 구독해 받은 이벤트를 그대로(가공·요약 없이) 세션 단위 실행 로그에 발생 순서대로 덧붙인다.
LLM 을 사용하지 않는다. 저장에 실패해도 예외를 밖으로 던지지 않아 메인 Agent 대화는 계속된다.
"""
from __future__ import annotations

import logging
from typing import Callable, Protocol

from app.events.bus import Event, EventBus

logger = logging.getLogger(__name__)


class LogSink(Protocol):
    def append(self, event: Event) -> None: ...


class LoggingAgent:
    uses_llm = False

    def __init__(self, sink: LogSink):
        self.sink = sink
        self.saved = 0
        self.failed = 0
        self._unsubscribe: Callable[[], None] | None = None

    def attach(self, bus: EventBus) -> "LoggingAgent":
        self._unsubscribe = bus.subscribe(self.handle)
        return self

    def detach(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    def handle(self, event: Event) -> None:
        try:
            self.sink.append(event)
            self.saved += 1
        except Exception:  # noqa: BLE001 - 로그 저장 실패가 대화를 멈추지 않도록
            self.failed += 1
            logger.warning("실행 로그 저장 실패 (session=%s, seq=%s)", event.session_id, event.seq)
