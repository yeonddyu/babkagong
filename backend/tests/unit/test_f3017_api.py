"""F3017 백엔드 API 서버 - 단위 테스트 (FastAPI TestClient, Mock 외부 API, 메모리 DB)."""
from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.main import build_deps, create_app
from tests.unit.agent_fixtures import NOW, TODAY, make_registry, make_session


@pytest.fixture
def client(make_settings):
    settings = replace(make_settings(), kma_api_key="test-kma", database_url="sqlite://", openai_api_key=None)
    deps = build_deps(settings, registry=make_registry(make_settings, make_session()),
                      agent_kwargs={"today_fn": lambda: TODAY, "now_fn": lambda: NOW})
    return TestClient(create_app(deps=deps))


def test_openapi_routes_are_separate(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths) == {"/api/health", "/api/stations", "/api/chat", "/api/chat/stream", "/api/plans", "/api/plans/{plan_id}", "/api/logs",
                          "/api/logs/{session_id}"}
    assert set(paths["/api/logs/{session_id}"]) == {"get", "delete"}  # 로그 수정(PUT/PATCH) 없음
    assert set(paths["/api/plans/{plan_id}"]) == {"get", "put", "delete"}
    assert client.get("/docs").status_code == 200


def test_health_hides_key_values(client):
    body = client.get("/api/health").json()
    assert body["api_keys"]["REDTABLE_API_KEY"] is True and body["api_keys"]["OPENAI_API_KEY"] is False
    assert "test-redtable" not in str(body)
    assert body["llm"]["available"] is False and set(body["tools"]) >= {"search_restaurant_candidates", "get_weather_context"}


def test_chat_flow_logs_and_save(client):
    r = client.post("/api/chat", json={"message": "내일 12시 강남역 1만원 이하 점심 먹고 카공"})
    assert r.status_code == 200
    body = r.json()
    sid = body["session_id"]
    assert body["intent"] == "recommend" and body["recommendations"][0]["name"] == "김치찌개집"
    assert body["events"][0]["type"] == "run_start" and body["elapsed_ms"] >= 0
    # 같은 세션 후속 요청 + 저장
    saved = client.post("/api/chat", json={"message": "이 코스로 저장해줘", "session_id": sid}).json()
    plan_id = saved["saved_plan"]["id"]
    assert client.get(f"/api/plans/{plan_id}").json()["restaurant_name"] == "김치찌개집"
    # 실행 로그: 목록 → 상세(순서) → 삭제
    sessions = client.get("/api/logs").json()["sessions"]
    assert sessions[0]["session_id"] == sid and sessions[0]["run_count"] == 2
    events = client.get(f"/api/logs/{sid}").json()["events"]
    assert events[0]["type"] == "run_start" and len(events) == len(body["events"]) + len(saved["events"])
    assert client.delete(f"/api/logs/{sid}").json()["deleted"] is True
    assert client.get(f"/api/logs/{sid}").status_code == 404
    assert client.put(f"/api/logs/{sid}", json={}).status_code == 405


def test_chat_area_from_ui(client):
    body = client.post("/api/chat", json={"message": "점심 추천해줘", "area": "역삼역"}).json()
    assert body["conditions"]["preference"]["area"] == "역삼역"


def test_plan_crud_and_conflict(client):
    base = {"title": "A", "plan_date": "2026-11-20", "start_time": "12:00", "end_time": "14:00", "restaurant_name": "식당"}
    a = client.post("/api/plans", json=base)
    assert a.status_code == 201 and a.json()["conflicts"] == []
    b = client.post("/api/plans", json={**base, "title": "B", "start_time": "13:00", "end_time": "15:00"}).json()
    assert [c["id"] for c in b["conflicts"]] == [a.json()["plan"]["id"]]
    pid = b["plan"]["id"]
    upd = client.put(f"/api/plans/{pid}", json={"start_time": "15:00", "end_time": "16:00"}).json()
    assert upd["plan"]["start_time"] == "15:00:00" and upd["conflicts"] == []
    assert [p["title"] for p in client.get("/api/plans").json()["plans"]] == ["A", "B"]
    assert client.get("/api/plans", params={"date": "2026-11-21"}).json()["plans"] == []
    assert client.delete(f"/api/plans/{pid}").json()["deleted"] is True
    assert client.get(f"/api/plans/{pid}").status_code == 404


def test_validation_errors_use_common_format(client):
    r = client.post("/api/plans", json={"title": "x", "plan_date": "2026-11-20", "start_time": "15:00", "end_time": "12:00",
                                        "restaurant_name": "y"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "INVALID_INPUT"
    assert client.post("/api/chat", json={"message": ""}).json()["detail"]["code"] == "INVALID_INPUT"
    bad = client.put("/api/plans/999", json={"title": "x"})
    assert bad.status_code == 404 and bad.json()["detail"] == {"code": "NOT_FOUND", "message": "계획을 찾을 수 없어요."}


def test_internal_error_hidden(client):
    client.app.state.deps.agent.run = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret stack detail"))
    r = client.post("/api/chat", json={"message": "강남역 점심"})
    assert r.status_code == 500 and "secret" not in r.text and r.json()["detail"]["code"] == "INTERNAL_ERROR"
