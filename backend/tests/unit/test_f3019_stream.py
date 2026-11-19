"""F3019 실행 과정 실시간 스트림(/api/chat/stream) - 단위 테스트."""
from __future__ import annotations

import json

from tests.unit.test_f3017_api import client  # noqa: F401 - fixture 재사용


def parse(text: str):
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_stream_progress_then_result(client):  # noqa: F811
    r = client.post("/api/chat/stream", json={"message": "강남역 1만원 이하 12시 점심", "session_id": "live"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = parse(r.text)
    kinds = [k for k, _ in events]
    assert kinds[-1] == "result" and set(kinds[:-1]) == {"progress"}
    progress = [d for k, d in events if k == "progress"]
    assert progress[0]["type"] == "run_start" and progress[-1]["type"] == "run_end"
    assert [p["seq"] for p in progress] == list(range(1, len(progress) + 1))
    assert any(p["type"] == "tool_call" for p in progress)
    result = events[-1][1]
    assert result["session_id"] == "live" and result["recommendations"]
    assert len(result["events"]) == len(progress)


def test_stream_internal_error_hidden(client):  # noqa: F811
    client.app.state.deps.agent.run = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret detail"))
    events = parse(client.post("/api/chat/stream", json={"message": "강남역"}).text)
    assert events == [("error", {"code": "INTERNAL_ERROR", "message": "요청을 처리하는 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요."})]
