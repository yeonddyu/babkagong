"""NF3001 점검: .env 의 실제 키 값이 저장소 추적 파일·문서·빌드 결과에 들어 있는지 검사한다.

키 값은 출력하지 않고 포함된 파일 경로만 보고한다.
실행 (저장소 루트에서): .venv/bin/python backend/scripts/check_secrets.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import urllib.parse

from dotenv import dotenv_values

ROOT = pathlib.Path(__file__).resolve().parents[2]


def main() -> int:
    values = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v and len(v) >= 12 and k.endswith(("KEY", "TOKEN"))}
    secrets: set[str] = set()
    for v in values.values():
        secrets |= {v, urllib.parse.unquote(v), urllib.parse.quote(v, safe="")}
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    extra = [p for d in ("docs", "frontend/dist") for p in (ROOT / d).rglob("*") if p.is_file()]
    paths = {ROOT / f for f in files} | set(extra)
    hits = []
    for p in sorted(paths):
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        if any(s in text for s in secrets):
            hits.append(str(p.relative_to(ROOT)))
    print(f"검사한 키 {len(values)}개, 파일 {len(paths)}개, 키가 포함된 파일: {hits or '없음'}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
