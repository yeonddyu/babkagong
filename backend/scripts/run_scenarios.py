"""대표 시나리오 검증 (요구사항정의서 4.7) — 실제 캐시와 외부 API 를 사용한다.

각 시나리오의 최종 응답, 실행 로그(단계·Tool 호출·재계획), 기대 동작과 실제 동작의 차이를 기록한다.
결과: docs/scenario_results.md, 실행 로그 샘플: docs/samples/*.json
실행 (backend/ 에서): ../.venv/bin/python -m scripts.run_scenarios
"""
from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from app.agent.graph import MainAgent
from app.core.config import REPO_ROOT, load_settings
from app.core.llm_provider import create_llm, llm_status
from app.datasets.cache import now_kst
from app.events.bus import EventBus
from app.events.logging_agent import LoggingAgent
from app.storage.db import init_db, make_engine, make_session_factory
from app.storage.logs import LogRepository
from app.storage.plans import PlanRepository
from app.storage.sessions import SqliteMemoryStore
from app.tools.catalog import build_default_registry

DOCS = REPO_ROOT / "docs"


def make_agent(settings, *, use_llm: bool = True):
    engine = make_engine("sqlite://")
    init_db(engine)
    sf = make_session_factory(engine)
    logs, plans = LogRepository(sf), PlanRepository(sf)
    bus = EventBus()
    LoggingAgent(logs).attach(bus)
    agent = MainAgent(build_default_registry(settings), llm=create_llm(settings) if use_llm else None,
                      max_replans=settings.max_replans, memory=SqliteMemoryStore(sf), bus=bus, plan_repo=plans,
                      seed_fn=lambda: 0)
    return agent, logs, plans


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    body = result["response"]
    events = result["events"]
    return {
        "intent": body["intent"],
        "decided_by": body["decided_by"],
        "stages": [e["stage"] for e in events if e["type"] == "stage_start"],
        "tool_calls": [f"{c['tool']}{'(재사용)' if c['reused'] else ''}:{'ok' if c['ok'] else c['error_code']}" for c in result["tool_calls"]],
        "fresh_tool_calls": sum(1 for c in result["tool_calls"] if not c["reused"]),
        "replans": [f"{h['count']}:{h['strategy']}" for h in result["replans"]],
        "stop_reason": result["stop_reason"],
        "recommendations": [r["name"] for r in body["recommendations"]],
        "excluded": len(body["excluded"]),
        "notices": body["notices"],
        "saved_plan": (body.get("saved_plan") or {}).get("id"),
        "conflicts": [c["id"] for c in body.get("plan_conflicts", [])],
    }


Check = Callable[[dict[str, Any], dict[str, Any]], tuple[bool, str]]


def scenarios(settings) -> list[dict[str, Any]]:
    no_kma = replace(settings, kma_api_key=None)
    return [
        {"id": "S1", "title": "제약을 한 번에 충족", "session": "S1",
         "message": "역삼역에서 1만 5천원 이하로 12시에 점심 먹고 카공할래",
         "expected": "재계획 없이 예산 이하 메뉴가 확인된 식당 + 주변 카페 추천",
         "check": lambda s, r: (bool(s["recommendations"]) and not s["replans"], "추천 있음·재계획 없음")},
        {"id": "S2", "title": "재계획이 필요한 요청", "session": "S2",
         "use_llm": False,
         "message": "역삼역에서 일식 7,000원 이하로 12시 점심",
         "expected": "첫 상세조회 묶음에서 충족 0건 → 다음 묶음 재계획 후 추천, 이미 호출한 Tool 재호출 없음",
         "check": lambda s, r: (s["replans"][:1] == ["1:next_batch"] and bool(s["recommendations"])
                                and len({(c["tool"], json.dumps(c["args"], sort_keys=True)) for c in r["tool_calls"] if not c["reused"]})
                                == s["fresh_tool_calls"], "다음 묶음 재계획 후 추천·중복 호출 없음")},
        {"id": "S3", "title": "재계획 상한 도달", "session": "S3",
         "message": "역삼역 1천원 이하 점심",
         "expected": "재계획 3회 후 중단, 사유와 조건 조정 제안",
         "check": lambda s, r: (len(s["replans"]) == 3 and "상한" in (s["stop_reason"] or "") and bool(r["response"]["suggestions"]),
                                "재계획 3회·상한 사유·제안")},
        {"id": "S4", "title": "Tool 하나가 실패 (기상청 키 제거)", "session": "S4", "settings": no_kma,
         "message": "강남역 점심 먹고 카공할 곳 추천해줘",
         "expected": "날씨 Tool 이 MISSING_API_KEY 로 실패해도 나머지 단계 진행, 안내 표시, 기본 정책으로 추천 제공",
         "check": lambda s, r: (any("MISSING_API_KEY" in t for t in s["tool_calls"]) and bool(s["recommendations"]) and bool(s["notices"]),
                                "실패 Tool 존재·추천 계속·안내")},
        {"id": "S5", "title": "Tool 이 필요 없는 요청 (인사)", "session": "S5", "message": "안녕!",
         "expected": "계획 생략, Tool 호출 0회",
         "check": lambda s, r: (s["fresh_tool_calls"] == 0 and "plan" not in s["stages"], "Tool 0회·plan 단계 없음")},
        {"id": "S6", "title": "Tool 이 필요 없는 요청 (사용법)", "session": "S6", "message": "사용법 알려줘",
         "expected": "사용법 안내, Tool 호출 0회",
         "check": lambda s, r: (s["fresh_tool_calls"] == 0, "Tool 0회")},
        {"id": "S7", "title": "날씨 반영 + 도보 선호", "session": "S7",
         "message": "오늘 비가 오는데 강남역에서 점심 먹고 카공하고 싶어. 많이 걷기는 싫어.",
         "expected": "기상청 예보 조회, 가까운 곳 선호 반영(카페 반경 300m), 말한 날씨와 예보가 다르면 안내",
         "check": lambda s, r: (any(t.startswith("get_weather_context:ok") for t in s["tool_calls"])
                                and all(c["args"]["radius_m"] == 300 for c in r["tool_calls"] if c["tool"] == "search_nearby_cafes"),
                                "날씨 조회 성공·카페 반경 300m")},
        {"id": "S8", "title": "후속 요청 맥락 유지", "session": "S1",
         "message": "같은 조건에서 한식 말고 일식으로 바꿔줘",
         "expected": "S1 의 지역·예산·시각 유지, 음식 종류만 일식으로 변경",
         "check": lambda s, r: (r["conditions"].preference.food_type == "일식" and r["conditions"].constraint.budget_max == 15000
                                and r["conditions"].preference.area == "역삼역", "변경 필드만 갱신")},
        {"id": "S9", "title": "계획 저장 (Tool 아님)", "session": "S1", "message": "이 코스로 저장해줘",
         "expected": "직전 추천 1번을 날짜·시각과 함께 저장, Tool 호출 0회",
         "check": lambda s, r: (s["saved_plan"] is not None and s["fresh_tool_calls"] == 0, "저장됨·Tool 0회")},
        {"id": "S10", "title": "같은 시간대 두 번째 저장 → 충돌 안내", "session": "S1", "message": "2번 코스도 저장해줘",
         "expected": "저장은 되고 겹치는 계획을 함께 안내",
         "check": lambda s, r: (s["saved_plan"] is not None and bool(s["conflicts"]), "저장됨·충돌 안내")},
    ]


def main() -> int:
    settings = load_settings()
    agent, logs, _ = make_agent(settings)
    alt_agents: dict[int, Any] = {}
    rows = []
    for sc in scenarios(settings):
        runner = agent
        if not sc.get("use_llm", True):
            runner = make_agent(settings, use_llm=False)[0]
        elif "settings" in sc:
            key = id(sc["settings"])
            alt_agents.setdefault(key, make_agent(sc["settings"])[0])
            runner = alt_agents[key]
        t0 = time.perf_counter()
        result = runner.run(sc["message"], session_id=sc["session"])
        elapsed = time.perf_counter() - t0
        summary = summarize(result)
        ok, criterion = sc["check"](summary, result)
        rows.append({**{k: sc[k] for k in ("id", "title", "message", "expected")}, "elapsed_s": round(elapsed, 2),
                     "pass": ok, "criterion": criterion, "summary": summary, "final": result["response"]["message"],
                     "run_id": result["run_id"], "session": sc["session"]})
        print(f"[{'PASS' if ok else 'FAIL'}] {sc['id']} {sc['title']} ({elapsed:.2f}s) {summary['replans']} {summary['recommendations']}", flush=True)
        if sc["id"] == "S1":
            sample_full = result
        if sc["id"] == "S3":
            sample_replan = result

    samples = DOCS / "samples"
    samples.mkdir(parents=True, exist_ok=True)
    for name, res in (("run_log_S1_full.json", sample_full), ("run_log_S3_replan_limit.json", sample_replan)):
        stored = [e for e in logs.get_session(res["session_id"]) if e["run_id"] == res["run_id"]]
        (samples / name).write_text(json.dumps({"message_by_scenario": name, "run_id": res["run_id"],
                                                "final_message": res["response"]["message"], "stored_log": stored},
                                               ensure_ascii=False, indent=2), encoding="utf-8")

    st = llm_status(settings)
    lines = [
        "# 대표 시나리오 검증 결과 (요구사항정의서 4.7)", "",
        f"- 실행 일시: {now_kst().strftime('%Y-%m-%d %H:%M')} KST, 명령: `cd backend && ../.venv/bin/python -m scripts.run_scenarios`",
        "- 데이터: 유효한 로컬 캐시를 재사용하고 필요한 외부 API를 호출. Tool별 실제 실행은 아래 기록 참조.",
        f"- 요청 분석: {'LLM 사용 (' + str(st.model) + ')' if st.available else '규칙 사용 (LLM 미설정)'}. 최종 문장은 구조화된 결과로 생성.",
        "- 실행 로그 샘플: `docs/samples/run_log_S1_full.json`(대표 요청 1건 전체), `docs/samples/run_log_S3_replan_limit.json`(재계획 사례)",
        "- 후보를 고르는 seed는 0으로 고정. S2는 규칙 분석을 사용해 현재 캐시에서 재계획 후 추천을 검증한다. "
        "캐시가 바뀌면 결과가 달라질 수 있으며, 고정 데이터 검증은 `test_f3009_replan.py`에서 수행한다.", "",
        "| ID | 시나리오 | 결과 | 시간(초) | Tool 호출(신규) | 재계획 | 추천 |", "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        s = r["summary"]
        lines.append(f"| {r['id']} | {r['title']} | {'PASS' if r['pass'] else 'FAIL'} | {r['elapsed_s']} | {s['fresh_tool_calls']} | "
                     f"{', '.join(s['replans']) or '-'} | {', '.join(s['recommendations'][:3]) or '-'} |")
    lines.append("")
    for r in rows:
        s = r["summary"]
        lines += [f"## {r['id']}. {r['title']}", "", f"- 요청: \"{r['message']}\" (세션 {r['session']})", f"- 기대 동작: {r['expected']}",
                  f"- 판정 기준: {r['criterion']} → **{'PASS' if r['pass'] else 'FAIL'}**",
                  f"- 단계: {' → '.join(x for x in s['stages'] if x)}",
                  f"- Tool 호출: {', '.join(s['tool_calls']) or '없음'}",
                  f"- 재계획: {', '.join(s['replans']) or '없음'}" + (f" / 중단 사유: {s['stop_reason']}" if s["stop_reason"] else ""),
                  f"- 제외 후보 수: {s['excluded']}, 안내: {' / '.join(s['notices']) or '없음'}",
                  "- 최종 응답:", "", "```", r["final"], "```", "",
                  f"- 기대와 차이: {'없음' if r['pass'] else '판정 기준 미충족 — 원인 분석 필요'}", ""]
    (DOCS / "scenario_results.md").write_text("\n".join(lines), encoding="utf-8")
    passed = sum(r["pass"] for r in rows)
    print("PASS", passed, "/", len(rows))
    return int(passed != len(rows))


if __name__ == "__main__":
    raise SystemExit(main())
