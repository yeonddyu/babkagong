"""외부 API 실제 연결 검증 스크립트.

- .env 의 키로 각 API 엔드포인트를 1회씩 호출하고 HTTP 상태·정상 여부·주요 필드를 기록한다.
- 키가 없으면 해당 항목을 BLOCKED 로 기록하고 호출하지 않는다 (공개 sample 키 / 잘못된 키 확인 제외).
- 출력 URL 의 비밀키는 마스킹한다. 원본 응답은 저장하지 않는다.

실행 (backend/ 에서): ../.venv/bin/python -m scripts.verify_apis
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import requests

from app.clients.kakao_local import CATEGORY_URL
from app.clients.redtable import BASE_URL as REDTABLE_URL
from app.clients.redtable import ENDPOINT_MENU_KOREAN, ENDPOINT_OPERATION, ENDPOINT_RESTAURANT
from app.clients.seoul_opendata import BASE_URL as SEOUL_URL
from app.clients.seoul_opendata import SERVICE_GANGNAM_GENERAL_RESTAURANT
from app.core.config import load_settings
from app.core.geo import STATIONS

KST = timezone(timedelta(hours=9))
TIMEOUT = 20


def mask(text: str, *secrets: str | None) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return re.sub(r"(serviceKey=)[^&]+", r"\1***", text)


def fields_of(obj) -> list[str]:
    return sorted(obj.keys()) if isinstance(obj, dict) else []


def check(name, url, *, params=None, headers=None, secrets=(), extract):
    entry = {"name": name, "checked_at": datetime.now(KST).isoformat(timespec="seconds")}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        entry["request_url"] = mask(resp.url, *secrets)
        entry["http_status"] = resp.status_code
        entry.update(extract(resp))
    except requests.Timeout:
        entry.update(result="FAIL", note="TIMEOUT")
    except Exception as exc:  # noqa: BLE001
        entry.update(result="FAIL", note=type(exc).__name__)
    return entry


def blocked(name, url, env):
    return {"name": name, "request_url": url, "http_status": None, "result": "BLOCKED", "note": f"{env} 미설정 - 호출하지 않음"}


def redtable_extract(resp):
    try:
        data = resp.json()
    except ValueError:
        return {"result": "FAIL", "note": "JSON 아님"}
    header = data.get("header", {})
    body = data.get("body") or []
    ok = resp.status_code == 200 and str(header.get("resultCode")) == "00"
    return {
        "result": "PASS" if ok else "FAIL",
        "result_code": header.get("resultCode"), "result_msg": header.get("resultMsg"),
        "total_count": header.get("totalCount"), "rows": len(body),
        "fields": fields_of(body[0]) if body else [],
    }


def seoul_extract(resp):
    text = resp.text.lstrip()
    if text.startswith("<"):
        code = re.search(r"<CODE>([^<]+)</CODE>", text)
        return {"result": "FAIL", "result_code": code.group(1) if code else None}
    block = resp.json().get(SERVICE_GANGNAM_GENERAL_RESTAURANT, {})
    rows = block.get("row") or []
    code = (block.get("RESULT") or {}).get("CODE")
    return {
        "result": "PASS" if code == "INFO-000" else "FAIL", "result_code": code,
        "total_count": block.get("list_total_count"), "rows": len(rows), "fields": fields_of(rows[0]) if rows else [],
    }


def kakao_extract(resp):
    data = resp.json()
    docs = data.get("documents") or []
    return {
        "result": "PASS" if resp.status_code == 200 else "FAIL",
        "total_count": (data.get("meta") or {}).get("total_count"), "rows": len(docs),
        "fields": fields_of(docs[0]) if docs else [], "error_type": data.get("errorType"),
    }


def expect_rejected(extract):
    """잘못된 키 확인용: 거부되면 PASS (오류 처리 검증)."""

    def _inner(resp):
        info = extract(resp)
        info["result"] = "PASS(거부 확인)" if resp.status_code in (401, 403) or info.get("result") == "FAIL" else "UNEXPECTED"
        return info

    return _inner


def main() -> None:
    s = load_settings()
    results = []

    # 1. 서울관광재단 음식관광 API (레드테이블)
    for label, ep in [("식당기본정보", ENDPOINT_RESTAURANT), ("메뉴정보 한국어", ENDPOINT_MENU_KOREAN), ("식당운영정보", ENDPOINT_OPERATION)]:
        name = f"[서울관광재단] {label} {ep}"
        if s.redtable_api_key:
            results.append(check(name, REDTABLE_URL + ep, params={"serviceKey": s.redtable_api_key, "pageNo": 1},
                                 secrets=(s.redtable_api_key,), extract=redtable_extract))
        else:
            results.append(blocked(name, f"{REDTABLE_URL}{ep}?serviceKey=***&pageNo=1", "REDTABLE_API_KEY"))
    results.append(check("[서울관광재단] 식당기본정보 - 잘못된 키 거부 확인", REDTABLE_URL + ENDPOINT_RESTAURANT,
                         params={"serviceKey": "INVALID", "pageNo": 1}, extract=expect_rejected(redtable_extract)))

    # 2. 서울 열린데이터광장 (강남구 일반음식점 인허가)
    svc = SERVICE_GANGNAM_GENERAL_RESTAURANT
    results.append(check(f"[서울 열린데이터광장] {svc} - 공개 sample 키(1~5건)", f"{SEOUL_URL}/sample/json/{svc}/1/5/",
                         extract=seoul_extract))
    if s.seoul_openapi_key:
        results.append(check(f"[서울 열린데이터광장] {svc} - 개인 키(1~1000건)", f"{SEOUL_URL}/{s.seoul_openapi_key}/json/{svc}/1/1000/",
                             secrets=(s.seoul_openapi_key,), extract=seoul_extract))
    else:
        results.append(blocked(f"[서울 열린데이터광장] {svc} - 개인 키(1~1000건)", f"{SEOUL_URL}/***/json/{svc}/1/1000/", "SEOUL_OPENAPI_KEY"))

    # 3. 카카오 로컬 API
    lat, lng = STATIONS["강남역"]
    params = {"category_group_code": "CE7", "x": lng, "y": lat, "radius": 300, "sort": "distance", "size": 15}
    if s.kakao_rest_api_key:
        results.append(check("[카카오 로컬] 카테고리 검색 CE7 (강남역 300m)", CATEGORY_URL, params=params,
                             headers={"Authorization": f"KakaoAK {s.kakao_rest_api_key}"}, secrets=(s.kakao_rest_api_key,),
                             extract=kakao_extract))
    else:
        results.append(blocked("[카카오 로컬] 카테고리 검색 CE7 (강남역 300m)", CATEGORY_URL + "?category_group_code=CE7&...", "KAKAO_REST_API_KEY"))
    results.append(check("[카카오 로컬] 잘못된 키 거부 확인", CATEGORY_URL, params=params,
                         headers={"Authorization": "KakaoAK INVALID"}, extract=expect_rejected(kakao_extract)))

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
