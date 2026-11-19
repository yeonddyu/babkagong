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
from app.clients.seoul_opendata import SERVICE_GANGNAM_GENERAL_RESTAURANT, SERVICE_GANGNAM_REST_FOOD
from app.clients.kma import BASE_URL as KMA_URL, latlon_to_grid
from app.tools.weather import latest_base
from app.datasets.cache import now_kst
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


def seoul_extract(resp, service=SERVICE_GANGNAM_GENERAL_RESTAURANT):
    text = resp.text.lstrip()
    if text.startswith("<"):
        code = re.search(r"<CODE>([^<]+)</CODE>", text)
        return {"result": "FAIL", "result_code": code.group(1) if code else None}
    block = resp.json().get(service, {})
    rows = block.get("row") or []
    code = (block.get("RESULT") or {}).get("CODE")
    return {
        "result": "PASS" if code == "INFO-000" else "FAIL", "result_code": code,
        "total_count": block.get("list_total_count"), "rows": len(rows), "fields": fields_of(rows[0]) if rows else [],
    }


def kma_extract(resp):
    text = resp.text.lstrip()
    if text.startswith("<"):
        return {"result": "FAIL", "note": "XML 오류 응답"}
    data = resp.json().get("response", {})
    header, body = data.get("header", {}), data.get("body", {})
    items = (body.get("items") or {}).get("item") or []
    return {"result": "PASS" if header.get("resultCode") == "00" else "FAIL", "result_code": header.get("resultCode"),
            "total_count": body.get("totalCount"), "rows": len(items), "fields": fields_of(items[0]) if items else [],
            "categories": sorted({i["category"] for i in items})}


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

    if s.seoul_openapi_key:
        results.append(check(f"[서울 열린데이터광장] {SERVICE_GANGNAM_REST_FOOD} - 개인 키(1~5건, 보조 카페)",
                             f"{SEOUL_URL}/{s.seoul_openapi_key}/json/{SERVICE_GANGNAM_REST_FOOD}/1/5/", secrets=(s.seoul_openapi_key,),
                             extract=lambda r: seoul_extract(r, SERVICE_GANGNAM_REST_FOOD)))
    else:
        results.append(blocked(f"[서울 열린데이터광장] {SERVICE_GANGNAM_REST_FOOD}", f"{SEOUL_URL}/***/json/{SERVICE_GANGNAM_REST_FOOD}/1/5/", "SEOUL_OPENAPI_KEY"))

    # 4. 기상청 단기예보
    base = latest_base(now_kst())
    nx, ny = latlon_to_grid(*STATIONS["강남역"])
    kma_q = f"&pageNo=1&numOfRows=100&dataType=JSON&base_date={base:%Y%m%d}&base_time={base:%H%M}&nx={nx}&ny={ny}"
    if s.kma_api_key:
        results.append(check("[기상청] 단기예보 getVilageFcst (강남역 격자)", f"{KMA_URL}?serviceKey={s.kma_api_key}{kma_q}",
                             secrets=(s.kma_api_key,), extract=kma_extract))
    else:
        results.append(blocked("[기상청] 단기예보 getVilageFcst", f"{KMA_URL}?serviceKey=***{kma_q}", "KMA_API_KEY"))

    # 5. OpenAI (키 존재 여부만, 키가 있을 때만 모델 목록 조회)
    if s.openai_api_key:
        results.append(check("[OpenAI] 모델 목록", "https://api.openai.com/v1/models",
                             headers={"Authorization": f"Bearer {s.openai_api_key}"}, secrets=(s.openai_api_key,),
                             extract=lambda r: {"result": "PASS" if r.status_code == 200 else "FAIL"}))
    else:
        results.append(blocked("[OpenAI] Chat 모델", "https://api.openai.com/v1/...", "OPENAI_API_KEY"))
    results.append({"name": "[SSAFY GMS]", "request_url": "-", "http_status": None, "result": "EXCLUDED",
                    "note": f"GMS_API_KEY {'존재' if s.gms_api_key else '없음'} — 모델 연동은 범위 밖이라 호출하지 않음"})

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
