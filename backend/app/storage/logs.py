"""F3013·F3014 실행 로그 저장소. 추가·조회·삭제만 제공하고 수정 기능은 두지 않는다."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, delete, func, select
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

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._sf() as s:
            rows = s.execute(
                select(ExecutionLog.session_id, func.count(ExecutionLog.id), func.count(func.distinct(ExecutionLog.run_id)),
                       func.min(ExecutionLog.created_at), func.max(ExecutionLog.created_at))
                .group_by(ExecutionLog.session_id).order_by(func.max(ExecutionLog.created_at).desc())
            ).all()
            out = []
            for sid, events, runs, first, last in rows:
                first_msg = s.execute(
                    select(ExecutionLog.payload).where(ExecutionLog.session_id == sid, ExecutionLog.event_type == "run_start")
                    .order_by(ExecutionLog.id).limit(1)).scalar()
                out.append({"session_id": sid, "event_count": events, "run_count": runs,
                            "first_at": first.isoformat(), "last_at": last.isoformat(),
                            "first_message": (first_msg or {}).get("message")})
            return out

    def get_session(self, session_id: str) -> list[dict[str, Any]]:
        """저장된 순서(= 실행 순서)대로 반환."""
        with self._sf() as s:
            rows = s.scalars(select(ExecutionLog).where(ExecutionLog.session_id == session_id).order_by(ExecutionLog.id)).all()
            return [r.to_dict() for r in rows]

    def delete_session(self, session_id: str) -> int:
        with self._sf() as s, s.begin():
            return s.execute(delete(ExecutionLog).where(ExecutionLog.session_id == session_id)).rowcount or 0
