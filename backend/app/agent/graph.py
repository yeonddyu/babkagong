"""메인 Agent (LangGraph): 분석 → 계획 → 실행 → 응답."""
from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date, datetime
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.analysis import analyze
from app.agent.conditions import AnalysisResult, Conditions
from app.agent.execution import ExecutionData, ToolExecutor, run_cafes, run_candidates, run_details, run_weather
from app.agent.planning import CAFE_RADIUS_M, CAFE_TARGETS, Plan, build_plan
from app.datasets.cache import now_kst
from app.tools.registry import ToolRegistry


class AgentState(TypedDict, total=False):
    session_id: str
    run_id: str
    message: str
    area_hint: str | None
    previous: dict[str, Any] | None
    analysis: AnalysisResult
    conditions: Conditions
    plan: Plan
    executor: ToolExecutor
    data: ExecutionData
    response: dict[str, Any]


class MainAgent:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        llm: Any | None = None,
        today_fn: Callable[[], date] = lambda: now_kst().date(),
        now_fn: Callable[[], datetime] = now_kst,
    ):
        self.registry = registry
        self.llm = llm
        self.today_fn = today_fn
        self.now_fn = now_fn
        self.graph = self._build()

    # ------------------------------------------------------------ graph
    def _build(self):
        g = StateGraph(AgentState)
        g.add_node("analyze", self.analyze_node)
        g.add_node("plan", self.plan_node)
        g.add_node("execute", self.execute_node)
        g.add_node("respond", self.respond_node)
        g.add_edge(START, "analyze")
        g.add_conditional_edges("analyze", self._after_analyze, {"plan": "plan", "respond": "respond"})
        g.add_conditional_edges("plan", self._after_plan, {"execute": "execute", "respond": "respond"})
        g.add_edge("execute", "respond")
        g.add_edge("respond", END)
        return g.compile()

    def graph_structure(self) -> dict[str, list[str]]:
        drawable = self.graph.get_graph()
        return {"nodes": [n for n in drawable.nodes], "edges": [f"{e.source}->{e.target}" for e in drawable.edges]}

    # ------------------------------------------------------------ nodes
    def analyze_node(self, state: AgentState) -> dict[str, Any]:
        analysis = analyze(state["message"], self.today_fn(), self.llm)
        conditions = analysis.conditions
        if state.get("area_hint") and conditions.preference.area is None:
            conditions = conditions.model_copy(deep=True)
            conditions.preference.area = state["area_hint"]
        return {"analysis": analysis, "conditions": conditions}

    def _after_analyze(self, state: AgentState) -> str:
        return "plan" if state["analysis"].intent == "recommend" else "respond"

    def plan_node(self, state: AgentState) -> dict[str, Any]:
        return {"plan": build_plan(state["analysis"], state["conditions"], self.today_fn())}

    def _after_plan(self, state: AgentState) -> str:
        return "execute" if state["plan"].mode == "tools" else "respond"

    def execute_node(self, state: AgentState) -> dict[str, Any]:
        ex: ToolExecutor = state["executor"]
        data: ExecutionData = state["data"]
        cond: Conditions = state["conditions"]
        area = cond.preference.area
        tools = [s.tool for s in state["plan"].steps]
        today = self.today_fn()
        if "get_weather_context" in tools:
            run_weather(ex, data, cond, area, today)
        run_candidates(ex, data, cond, area)
        if data.candidates:
            run_details(ex, data)
            targets = [c for c in data.candidates[: data.detailed_count] if f"{c['source']}:{c['source_id']}" in data.details]
            run_cafes(ex, data, targets[:CAFE_TARGETS], CAFE_RADIUS_M)
        return {}

    def respond_node(self, state: AgentState) -> dict[str, Any]:
        analysis: AnalysisResult = state["analysis"]
        data: ExecutionData | None = state.get("data")
        recs = []
        if data:
            for c in data.candidates[: data.detailed_count]:
                key = f"{c['source']}:{c['source_id']}"
                if key in data.details:
                    recs.append({"restaurant": c, "detail": data.details[key], "cafes": (data.cafes.get(key) or {}).get("cafes", [])})
        return {"response": {"intent": analysis.intent, "recommendations": recs}}

    # ------------------------------------------------------------ run
    def run(self, message: str, *, session_id: str | None = None, area_hint: str | None = None) -> dict[str, Any]:
        state: AgentState = {
            "session_id": session_id or uuid.uuid4().hex,
            "run_id": uuid.uuid4().hex,
            "message": message,
            "area_hint": area_hint,
            "executor": ToolExecutor(self.registry),
            "data": ExecutionData(),
        }
        final = self.graph.invoke(state)
        ex: ToolExecutor = final["executor"]
        return {
            "session_id": final["session_id"],
            "run_id": final["run_id"],
            "analysis": final["analysis"],
            "conditions": final["conditions"],
            "plan": final.get("plan"),
            "tool_calls": [asdict(c) for c in ex.calls],
            "data": final["data"],
            "response": final["response"],
        }
