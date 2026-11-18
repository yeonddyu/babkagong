# 밥카공 Tool 명세서

대상 요구사항: F3001 ~ F3004 (3회차 요구사항정의서 기준)

## 1. 공통 규칙 (F3001)

### 1.1 Tool 구분

| 구분 | 값 | 설명 |
|---|---|---|
| 외부 API 툴 | `external_api` | 외부 API Client(`app/clients/*`)를 감싼 Tool |
| 로컬 서버 API 툴 | `local_server_api` | 이 서비스 서버가 가진 기능을 감싼 Tool (STEP 1 범위에는 등록 대상 없음, 구분 체계만 정의) |

사용자가 이미 정한 값을 저장하는 작업(계획 저장 등)은 Tool 로 두지 않는다.

### 1.2 공통 응답 형식

모든 Tool 은 `ToolRegistry.invoke()` 를 거쳐 아래 둘 중 하나로만 응답한다. 예외는 밖으로 전파되지 않는다 (NF3003).

```json
{"ok": true,  "data": {"...": "..."}, "error": null}
{"ok": false, "data": null, "error": {"code": "NO_RESULT", "message": "..."}}
```

### 1.3 오류 코드

| 코드 | 의미 | 재시도/재계획 |
|---|---|---|
| `MISSING_API_KEY` | `.env` 에 해당 API 키가 없음 | 재시도해도 결과 동일 → 재계획하지 않음 |
| `INVALID_INPUT` | 입력 스키마 검증 실패, 등록되지 않은 Tool | 입력을 고쳐 재호출 |
| `NO_RESULT` | 정상 호출했지만 조건에 맞는 결과 없음 | 조건 완화 후 재계획 가능 |
| `TIMEOUT` | 외부 API 응답 시간 초과 (`HTTP_TIMEOUT_SEC`, 기본 10초) | 재시도 가능 |
| `API_ERROR` | 인증 실패(401/403), 호출 한도 초과(429), 5xx, 응답 형식 오류, 예상 못한 예외 | 상황에 따라 재시도 |
| `DETAIL_NOT_AVAILABLE` | 해당 출처가 상세정보를 제공하지 않음 | 다른 출처 후보 선택 |

오류 메시지에는 API 키·내부 예외 상세를 넣지 않는다 (NF3002).

### 1.4 레지스트리

- 위치: `app/tools/registry.py`, 기본 구성: `app/tools/catalog.py::build_default_registry()`
- 명세 출력: `.venv/bin/python -m scripts.print_tools`
- LangChain 변환: `registry.as_langchain_tools()` → `StructuredTool` (args_schema = 입력 Pydantic 모델)
- Tool 이름 규칙: 소문자 snake_case, 설명은 “언제 쓰는지” 중심으로 20자 이상

## 2. Tool 목록

| 이름 | 구분 | 요구사항 | 제공처 |
|---|---|---|---|
