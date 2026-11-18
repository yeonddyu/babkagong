"""기본 Tool 레지스트리 구성 (F3001).

Agent 는 build_default_registry() 가 돌려준 레지스트리만 사용한다.
"""
from __future__ import annotations

from app.core.config import Settings, load_settings
from app.tools.registry import ToolRegistry


def build_default_registry(settings: Settings | None = None) -> ToolRegistry:
    settings = settings or load_settings()
    registry = ToolRegistry()
    # F3002~F3004 Tool 은 각 요구사항 구현 시 여기에 등록한다.
    return registry
