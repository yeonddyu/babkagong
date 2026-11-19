"""F3013 실행 로그 저장소. 수정 기능은 두지 않는다."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from app.events.bus import Event
from app.storage.db import Base


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(32))
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "session_id": self.session_id, "run_id": self.run_id, "seq": self.seq,
                "type": self.event_type, "stage": self.stage, "payload": self.payload,
                "timestamp": self.created_at.isoformat()}


class LogRepository:
    def __init__(self, session_factory: sessionmaker):
        self._sf = session_factory

    def append(self, event: Event) -> None:
        with self._sf() as s, s.begin():
            s.add(ExecutionLog(session_id=event.session_id, run_id=event.run_id, seq=event.seq, event_type=event.type,
                               stage=event.stage, payload=event.payload,
                               created_at=datetime.fromisoformat(event.timestamp)))

    def get_session(self, session_id: str) -> list[dict[str, Any]]:
        """저장된 순서(= 실행 순서)대로 반환."""
        with self._sf() as s:
            rows = s.scalars(select(ExecutionLog).where(ExecutionLog.session_id == session_id).order_by(ExecutionLog.id)).all()
            return [r.to_dict() for r in rows]
