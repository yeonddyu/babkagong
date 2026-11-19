"""F3012 실행 이벤트 발행·구독.

발행자(메인 Agent)는 EventBus.publish 만 호출하며 누가 구독하는지 모른다.
구독자 처리 중 예외가 나도 발행자에게 전파하지 않는다 (로깅 Agent 장애 격리).
"""
from __future__ import annotations

import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable

from app.datasets.cache import now_kst

logger = logging.getLogger(__name__)

EVENT_TYPES = (
    "run_start", "stage_start", "stage_end", "llm_decision", "plan_created",
    "tool_call", "tool_result", "tool_reuse", "replan", "error", "run_end",
)


@dataclass(frozen=True)
class Event:
    session_id: str
    run_id: str
    seq: int
    type: str
    stage: str | None
    payload: dict[str, Any]
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


Subscriber = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._lock = threading.Lock()

    def subscribe(self, handler: Subscriber) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(handler)

        def unsubscribe() -> None:
            with self._lock:
                if handler in self._subscribers:
                    self._subscribers.remove(handler)

        return unsubscribe

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event: Event) -> None:
        for handler in list(self._subscribers):
            try:
                handler(event)
            except Exception:  # noqa: BLE001 - 구독자 장애가 메인 Agent 를 멈추지 않도록
                logger.exception("이벤트 구독자 처리 실패 (type=%s)", event.type)


@dataclass
class RunPublisher:
    """한 번의 Agent 실행에 묶인 발행기. 세션·실행 ID 와 순번을 붙인다."""

    bus: EventBus
    session_id: str
    run_id: str
    clock: Callable[[], datetime] = now_kst
    events: list[Event] = field(default_factory=list)  # 이번 실행 응답에 포함할 사본

    def emit(self, type: str, stage: str | None = None, **payload: Any) -> Event:
        event = Event(self.session_id, self.run_id, len(self.events) + 1, type, stage,
                      _jsonable(payload), self.clock().isoformat(timespec="milliseconds"))
        self.events.append(event)
        self.bus.publish(event)
        return event


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
