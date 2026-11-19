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
    use_previous = analysis.is_followup or new.preference.area is None
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
    for rec in recommendations:
        r = rec["restaurant"]
        out.append({
            "restaurant": {k: r.get(k) for k in ("name", "source", "source_id", "road_address", "latitude", "longitude", "distance_m")},
            "menus": [{"name": m["name"], "price_krw": m.get("price_krw")} for m in rec.get("matched_menus", [])[:3]],
            "business_hours": rec.get("business_hours"),
            "cafes": [{k: c.get(k) for k in ("name", "source", "source_id", "road_address", "place_url", "distance_m")}
                      for c in rec.get("cafes", [])[:3]],
        })
    return out


def build_memory(conditions: Conditions, intent: str, recommendations: list[dict[str, Any]],
                 previous: dict[str, Any] | None) -> dict[str, Any]:
    memory = {
        "conditions": conditions.model_dump(mode="json"),
        "last_intent": intent,
        "recommendations": summarize_recommendations(recommendations) if recommendations else
        (previous or {}).get("recommendations", []) if intent != "recommend" else [],
    }
    return memory
