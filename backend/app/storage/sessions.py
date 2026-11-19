"""F3010 대화 맥락의 SQLite 저장 구현 (서버 재시작 후에도 세션 맥락 유지)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, delete
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from app.datasets.cache import now_kst
from app.storage.db import Base


class SessionMemoryRow(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SqliteMemoryStore:
    def __init__(self, session_factory: sessionmaker):
        self._sf = session_factory

    def load(self, session_id: str) -> dict[str, Any] | None:
        with self._sf() as s:
            row = s.get(SessionMemoryRow, session_id)
            return dict(row.memory) if row else None

    def save(self, session_id: str, memory: dict[str, Any]) -> None:
        with self._sf() as s, s.begin():
            row = s.get(SessionMemoryRow, session_id)
            if row is None:
                s.add(SessionMemoryRow(session_id=session_id, memory=memory, updated_at=now_kst()))
            else:
                row.memory = memory
                row.updated_at = now_kst()

    def delete(self, session_id: str) -> None:
        with self._sf() as s, s.begin():
            s.execute(delete(SessionMemoryRow).where(SessionMemoryRow.session_id == session_id))
