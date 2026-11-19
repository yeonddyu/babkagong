"""F3010 대화 맥락 유지.

보관: 직전 조건, 추천 요약(식당·카페 이름·출처·ID·주소·좌표·링크, 확인된 메뉴 가격 일부), 마지막 의도.
보관하지 않음: 외부 API 원본 응답, 전체 메뉴 목록, 제외 후보 상세.
병합 규칙: 후속 표현('같은 조건', '말고', '바꿔' 등)이 있거나 이번 발화에 지역이 없으면 직전 조건을
이어받고, 이번 발화에서 명시한 필드만 덮어쓴다. '처음부터/새로' 는 초기화한다.
"""
from __future__ import annotations

from typing import Any, Protocol

from app.agent.conditions import AnalysisResult, Conditions


class MemoryStore(Protocol):
    def load(self, session_id: str) -> dict[str, Any] | None: ...

    def save(self, session_id: str, memory: dict[str, Any]) -> None: ...


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def load(self, session_id: str) -> dict[str, Any] | None:
        return self._data.get(session_id)

    def save(self, session_id: str, memory: dict[str, Any]) -> None:
        self._data[session_id] = memory


def resolve_conditions(analysis: AnalysisResult, previous: dict[str, Any] | None) -> tuple[Conditions, list[str], bool]:
    """(적용 조건, 이번에 바뀐 필드, 이전 조건 사용 여부)."""
    new = analysis.conditions
    if analysis.reset or not previous or not previous.get("conditions") or analysis.intent != "recommend":
        return new, list(new.filled_fields()), False
    use_previous = analysis.is_followup or analysis.more or new.preference.area is None
    if not use_previous:
        return new, list(new.filled_fields()), False
    prev = Conditions.model_validate(previous["conditions"])
    merged = prev.merged_with(new)
    # 새 음식 종류를 고르면 이전 제외 목록 중 그 종류는 해제
    if new.preference.food_type and new.preference.food_type in merged.preference.exclude_food_types:
        merged.preference.exclude_food_types.remove(new.preference.food_type)
    return merged, list(new.filled_fields()), True


def summarize_recommendations(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in recommendations:
        out.append({
            "restaurant": {k: r.get(k) for k in ("name", "source", "source_id", "address", "latitude", "longitude", "distance_m", "area")},
            "menus": [{"name": m["name"], "price_krw": m.get("price_krw")} for m in r.get("matched_menus", [])[:3]],
            "business_hours": r.get("business_hours"),
            "cafes": [{k: c.get(k) for k in ("name", "source", "source_id", "road_address", "address", "place_url", "distance_m",
                                             "latitude", "longitude")}
                      for c in r.get("cafes", [])[:3]],
        })
    return out


def shown_keys(previous: dict[str, Any] | None) -> list[str]:
    return list((previous or {}).get("shown", []))


def shown_names(previous: dict[str, Any] | None) -> list[str]:
    return list((previous or {}).get("shown_names", []))


def normalize_place_name(name: str) -> str:
    """'더 보기' 중복 판단용 (괄호 지점명·공백 제거). ID 를 연결하지 않고 목록에서만 쓴다."""
    import re

    return re.sub(r"\(.*?\)|\s", "", name).lower()


def build_memory(conditions: Conditions, intent: str, recommendations: list[dict[str, Any]],
                 previous: dict[str, Any] | None, *, more: bool = False) -> dict[str, Any]:
    keys = [f"{r['source']}:{r['source_id']}" for r in recommendations]
    names = [normalize_place_name(r["name"]) for r in recommendations]
    memory = {
        "conditions": conditions.model_dump(mode="json"),
        "last_intent": intent,
        "recommendations": summarize_recommendations(recommendations) if recommendations else
        (previous or {}).get("recommendations", []) if intent != "recommend" else [],
        # '더 보기' 에서 다시 추천하지 않을 곳 (식별자만 보관)
        "shown": (shown_keys(previous) + keys) if more else keys,
        # 같은 가게가 다른 ID 로 중복 등록된 경우도 다시 보여 주지 않도록 이름도 기록
        "shown_names": (shown_names(previous) + names) if more else names,
    }
    return memory
