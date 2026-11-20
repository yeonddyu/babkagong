"""F3015·F3016 계획 저장소.

같은 날짜에 시간이 겹치는 계획이 있어도 저장은 막지 않고 겹치는 계획 목록을 함께 돌려준다.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import Date, DateTime, Float, Integer, String, Text, Time, select
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from app.datasets.cache import KST, now_kst
from app.storage.db import Base


class PlanRow(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100))
    plan_date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    area: Mapped[str | None] = mapped_column(String(10), nullable=True)
    restaurant_name: Mapped[str] = mapped_column(String(200))
    restaurant_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    restaurant_source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    restaurant_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    restaurant_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    restaurant_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    cafe_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cafe_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cafe_source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cafe_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cafe_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cafe_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    cafe_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlanBase(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    plan_date: date
    start_time: time
    end_time: time
    area: str | None = Field(default=None, max_length=30)
    restaurant_name: str = Field(min_length=1, max_length=200)
    restaurant_source: str | None = None
    restaurant_source_id: str | None = None
    restaurant_address: str | None = None
    restaurant_lat: float | None = Field(default=None, ge=33, le=39, description="지도 표시용 좌표 (추천 결과의 확인된 값)")
    restaurant_lng: float | None = Field(default=None, ge=124, le=132)
    cafe_name: str | None = None
    cafe_source: str | None = None
    cafe_source_id: str | None = None
    cafe_address: str | None = None
    cafe_url: str | None = None
    cafe_lat: float | None = Field(default=None, ge=33, le=39)
    cafe_lng: float | None = Field(default=None, ge=124, le=132)
    memo: str | None = Field(default=None, max_length=1000)
    session_id: str | None = None

    @model_validator(mode="after")
    def _times(self):
        if self.start_time >= self.end_time:
            raise ValueError("종료 시각은 시작 시각보다 늦어야 합니다")
        return self


class PlanCreate(PlanBase):
    pass


class PlanUpdate(BaseModel):
    """수정 가능한 핵심 값 (보낸 필드만 반영)."""

    title: str | None = Field(default=None, min_length=1, max_length=100)
    plan_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    restaurant_name: str | None = Field(default=None, min_length=1, max_length=200)
    cafe_name: str | None = None
    memo: str | None = Field(default=None, max_length=1000)


class PlanOut(PlanBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def _kst(cls, v: datetime) -> datetime:
        return v.replace(tzinfo=KST) if v.tzinfo is None else v  # SQLite 는 시간대를 저장하지 않음 (항상 KST 로 저장)


class ConflictOut(BaseModel):
    id: int
    title: str
    plan_date: date
    start_time: time
    end_time: time


class PlanNotFound(Exception):
    pass


class PlanRepository:
    def __init__(self, session_factory: sessionmaker, *, clock=now_kst):
        self._sf = session_factory
        self._clock = clock

    @staticmethod
    def _conflicts(s, plan_date: date, start: time, end: time, exclude_id: int | None = None) -> list[ConflictOut]:
        q = select(PlanRow).where(PlanRow.plan_date == plan_date, PlanRow.start_time < end, PlanRow.end_time > start)
        if exclude_id is not None:
            q = q.where(PlanRow.id != exclude_id)
        return [ConflictOut.model_validate(r, from_attributes=True) for r in s.scalars(q.order_by(PlanRow.start_time)).all()]

    def create(self, data: PlanCreate) -> tuple[PlanOut, list[ConflictOut]]:
        now = self._clock()
        with self._sf() as s, s.begin():
            conflicts = self._conflicts(s, data.plan_date, data.start_time, data.end_time)
            row = PlanRow(**data.model_dump(), created_at=now, updated_at=now)
            s.add(row)
            s.flush()
            return PlanOut.model_validate(row), conflicts

    def list(self, plan_date: date | None = None) -> list[PlanOut]:
        with self._sf() as s:
            q = select(PlanRow)
            if plan_date:
                q = q.where(PlanRow.plan_date == plan_date)
            rows = s.scalars(q.order_by(PlanRow.plan_date, PlanRow.start_time, PlanRow.id)).all()
            return [PlanOut.model_validate(r) for r in rows]

    def get(self, plan_id: int) -> PlanOut:
        with self._sf() as s:
            row = s.get(PlanRow, plan_id)
            if row is None:
                raise PlanNotFound(plan_id)
            return PlanOut.model_validate(row)

    def update(self, plan_id: int, changes: PlanUpdate) -> tuple[PlanOut, list[ConflictOut]]:
        """보낸 필드만 수정. 수정 후 시간이 겹치는 다른 계획을 함께 반환 (수정은 막지 않음)."""
        patch = changes.model_dump(exclude_unset=True)
        with self._sf() as s, s.begin():
            row = s.get(PlanRow, plan_id)
            if row is None:
                raise PlanNotFound(plan_id)
            merged = PlanBase.model_validate({**PlanOut.model_validate(row).model_dump(), **patch})  # 시각 검증
            for key in patch:
                setattr(row, key, getattr(merged, key))
            row.updated_at = self._clock()
            s.flush()
            conflicts = self._conflicts(s, row.plan_date, row.start_time, row.end_time, exclude_id=row.id)
            return PlanOut.model_validate(row), conflicts

    def delete(self, plan_id: int) -> None:
        with self._sf() as s, s.begin():
            row = s.get(PlanRow, plan_id)
            if row is None:
                raise PlanNotFound(plan_id)
            s.delete(row)

    def conflicts_of(self, plan: PlanOut) -> list[ConflictOut]:
        with self._sf() as s:
            return self._conflicts(s, plan.plan_date, plan.start_time, plan.end_time, exclude_id=plan.id)

    def as_dict(self, plan: PlanOut) -> dict[str, Any]:
        return plan.model_dump(mode="json")
