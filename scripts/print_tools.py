"""등록된 Tool 목록과 입출력 스키마를 출력한다 (F3001 확인용).

실행: .venv/bin/python -m scripts.print_tools
"""
from __future__ import annotations

import json

from app.tools.catalog import build_default_registry


def main() -> None:
    registry = build_default_registry()
    print(f"등록된 Tool 수: {len(registry.names())}")
    for spec in registry.describe():
        print("=" * 80)
        print(f"name       : {spec['name']}")
        print(f"kind       : {spec['kind']}")
        print(f"providers  : {', '.join(spec['providers'])}")
        print(f"description: {spec['description']}")
        print(f"error_codes: {', '.join(spec['error_codes'])}")
        print("input_schema:")
        print(json.dumps(spec["input_schema"], ensure_ascii=False, indent=2))
        print("output_schema (top-level properties):")
        print(json.dumps(list(spec["output_schema"].get("properties", {})), ensure_ascii=False))


if __name__ == "__main__":
    main()
