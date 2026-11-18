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
| `search_restaurant_candidates` | external_api | F3002 | 서울관광재단 음식관광 API(1순위), 서울 열린데이터광장 강남구 일반음식점 인허가(보완) |
| `get_restaurant_details` | external_api | F3003 | 서울관광재단 음식관광 API(식당기본정보·메뉴정보 한국어·식당운영정보), 강남구 인허가(기본정보만) |
| `search_nearby_cafes` | external_api | F3004 | 카카오 로컬 API (카테고리 검색 CE7) |

---

## 3. `search_restaurant_candidates` (F3002)

**설명(Agent 노출)**: 강남역 또는 역삼역 주변에서 식사할 음식점 후보 목록이 필요할 때 사용한다. 음식 종류와 영업 기준일로 거른 후보를 거리순으로 돌려준다. 각 후보의 `source`·`source_id` 는 `get_restaurant_details` 에 그대로 넘긴다. 카페는 `search_nearby_cafes` 로 찾는다.

### 입력

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|
| `area` | `"강남역" \| "역삼역"` | O | - | 검색 지역 (역 중심 반경 700m) |
| `food_type` | `"한식" \| "중식" \| "일식" \| "양식" \| "분식" \| "기타"` | X | 전체 | 음식 종류 |
| `reference_date` | `YYYY-MM-DD` | X | 오늘(KST) | 영업 여부 판단 기준일 |
| `max_results` | int 1~50 | X | 10 | 최대 결과 수 |

### 출력 `data`

| 필드 | 설명 |
|---|---|
| `area`, `center{latitude,longitude}`, `radius_m`, `food_type` | 실제 적용된 검색 조건 |
| `query_basis` | `requested_date`, `applied_date`, `default_applied`, `differs_from_request`, `notes[]` — 기본값 적용·요청과 실제 기준 차이를 명시 |
| `candidates[]` | `name`, `source`, `source_id`, `road_address`, `jibun_address`, `latitude`, `longitude`, `coordinate_note`, `distance_m`, `category`(출처 원본), `food_type`(정규화), `business_status`(인허가 출처만), `detail_available` |
| `source_status[]` | 출처별 `ok`, `returned`, `error_code`, `message`, `data_fetched_at`, `data_updated_at` |
| `skipped_possible_duplicates` | 보완 출처에서 이름·위치(30m 이내)가 1순위 후보와 같아 목록에서 뺀 수 |

### 동작 규칙

- 1순위 레드테이블 결과(거리순)로 `max_results` 를 채우지 못하면 강남구 인허가 데이터로 보충한다.
- 출처 ID 는 출처 내부에서만 유효하다. 레드테이블 `RSTR_ID` 와 인허가 `MGTNO` 를 같은 식당으로 연결하지 않는다.
  이름·위치가 같아 보이는 보완 행은 **연결하지 않고 목록에서 제외**만 하며 그 수를 `skipped_possible_duplicates` 로 알린다.
- 카페류 분류(`까페` 등)는 제외한다. 좌표가 없는 행은 거리 판단이 불가하므로 제외한다.
- 인허가 영업 판정: 인허가일 ≤ 기준일 < 폐업일. 오늘 이후는 현재 영업상태(`01 영업/정상`)로 판정. 휴업 이력은 데이터에 없다.
- 미래 기준일 → 오늘 기준으로 조회하고 `differs_from_request=true` + 사유를 `notes` 에 남긴다.
- 레드테이블은 기준일 개념이 없어 데이터 수집 시점 기준임을 `notes` 에 항상 남긴다.
- 강남역 서측(서초구)은 강남구 인허가 데이터에 없다는 점을 `notes` 에 남긴다.
- 인허가 X/Y(EPSG:5174)는 WGS84 로 변환하고 `coordinate_note` 에 변환 사실을 표시한다.

### 데이터 수집·캐시

두 API 모두 지역/ID 필터 파라미터가 없어 전체 페이지를 순회한 뒤, 두 역 중 한 곳에서 1.5km 이내 행만 `data/cache/*.json` 에 저장하고 `CACHE_TTL_HOURS`(기본 168시간) 동안 재사용한다. 첫 호출은 전체 페이지 수만큼 API 를 호출하므로 오래 걸릴 수 있다.

### 실패

| 상황 | 결과 |
|---|---|
| 입력 누락·범위 오류 | `INVALID_INPUT` (외부 호출 없음) |
| 두 출처 모두 키 없음 | `MISSING_API_KEY` |
| 한 출처만 실패 | `ok=true`, 해당 출처 `source_status.ok=false` + `error_code` |
| 두 출처 모두 실패 | 1순위 출처의 오류 코드 (`TIMEOUT`/`API_ERROR`) |
| 조회 성공·후보 0건 | `NO_RESULT` |

---

## 4. `get_restaurant_details` (F3003)

**설명(Agent 노출)**: `search_restaurant_candidates` 로 찾은 특정 음식점의 메뉴명·가격·영업시간·휴무일·편의시설을 확인해야 할 때 사용한다. 후보의 `source` 와 `source_id` 를 그대로 넣는다. 확인되지 않은 값은 null 이며, 상세정보를 제공하지 않는 출처의 후보는 `detail_available=false` 와 그 사유를 돌려준다.

### 입력

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `source` | `"seoul_tourism_redtable" \| "gangnam_general_restaurant_license"` | O | 후보 Tool 결과의 `source` |
| `source_id` | str (1~64자) | O | 후보 Tool 결과의 `source_id` (레드테이블 `RSTR_ID` / 인허가 `MGTNO`) |

### 출력 `data`

| 필드 | 설명 |
|---|---|
| `source`, `source_id` | 요청한 출처·식별자 |
| `basic` | `name`, `road_address`, `jibun_address`, `latitude`, `longitude`, `phone`, `category`, `license_type`, `business_status`(인허가만) |
| `detail_available` | 이 출처가 메뉴·운영정보를 제공하는지 |
| `detail_unavailable` | 제공 불가 시 `{code: "DETAIL_NOT_AVAILABLE", message}`, 아니면 null |
| `menus` | `[{menu_id, name, price_krw, is_local_specialty}]`. 확인 불가(제공 안 함·조회 실패) → null, 등록 메뉴 없음 → [] |
| `menu_status` | `found` / `not_found` / `unavailable` / `error` |
| `operation` | `business_hours`, `holidays`, `wifi`, `parking`, `standing_seats`, `floor_seats`, `reservation_method`, `barrier_free`, `delivery`, `kiosk`, `mobile_payment`, `representative_menu`, `homepage_url` (없는 값은 null) |
| `operation_status` | `found` / `not_found` / `unavailable` / `error` |
| `section_errors[]` | 메뉴·운영정보 조회 중 실패한 섹션의 `{section, code, message}` |
| `data_fetched_at` | 섹션별 데이터 수집 시각 |

### 동작 규칙

- 레드테이블 후보: 식당기본정보·메뉴정보(한국어)·식당운영정보를 **같은 출처의 `RSTR_ID`** 로만 연결한다.
- 인허가 후보: 기본정보만 반환하고 `detail_unavailable` 에 사유를 적는다. 이름·주소가 비슷한 레드테이블 식당의 메뉴를 가져오지 않는다 (해당 경로에서는 레드테이블 API 를 호출하지 않음).
- 값 변환: `Y`→true, `N`→false, 그 외/빈값→null. 가격이 없거나 0 이하 → null. 문자열 `"null"`·빈 문자열 → null.
- 메뉴 또는 운영정보 API 만 실패하면 기본정보와 나머지 섹션은 정상 반환하고 실패 섹션은 `status=error` + `section_errors` 로 알린다.
- 메뉴정보(약 57만 행)·운영정보 API 도 식당 ID 필터가 없어 전체 페이지를 순회한 뒤 서비스 지역 식당 ID 만 캐시한다.

### 실패

| 상황 | 결과 |
|---|---|
| `source`/`source_id` 누락·허용되지 않은 출처 | `INVALID_INPUT` |
| 해당 출처 키 없음 | `MISSING_API_KEY` |
| 서비스 지역 데이터에 없는 ID | `NO_RESULT` |
| 기본정보 조회 시간 초과 / API 오류 | `TIMEOUT` / `API_ERROR` |
| 상세정보 미제공 출처 | `ok=true` + `detail_unavailable.code = DETAIL_NOT_AVAILABLE` (기본정보는 유지) |

---

## 5. `search_nearby_cafes` (F3004)

**설명(Agent 노출)**: 식사할 음식점이 정해진 뒤 그 주변에서 카공(공부·작업)할 카페를 찾아야 할 때 사용한다. 음식점 후보의 latitude/longitude 를 넣으면 반경 안의 카페를 가까운 순으로 돌려준다. 영업시간·콘센트·와이파이·혼잡도는 이 Tool 로 확인할 수 없어 항상 null 이다.

### 입력

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|
| `latitude` | float 33~39 | O | - | 기준 위도 (F3002/F3003 결과의 `latitude`) |
| `longitude` | float 124~132 | O | - | 기준 경도 |
| `radius_m` | int 1~20000 | X | 500 | 검색 반경(m), 카카오 허용 범위 |
| `max_results` | int 1~675 | X | 10 | 최대 결과 수 (15건 × 최대 45페이지) |

### 출력 `data`

| 필드 | 설명 |
|---|---|
| `center`, `radius_m` | 적용된 검색 기준 |
| `total_count` | 카카오가 보고한 반경 내 카페 수 |
| `cafes[]` | `kakao_place_id`, `name`, `address`(지번), `road_address`, `latitude`, `longitude`, `distance_m`, `place_url`, `phone`, `category_name`, `opening_hours`=null, `power_outlet`=null, `wifi`=null, `congestion`=null |
| `not_provided_fields` | `["opening_hours","power_outlet","wifi","congestion"]` — 출처에서 확인할 수 없어 null 로 둔 항목 |
| `source` | `kakao_local_category_CE7` |

### 동작 규칙

- `category_group_code=CE7`, `sort=distance`, `size=15` 로 호출하고 `max_results` 를 채울 때까지 `page` 를 늘린다 (`is_end` 이면 중단).
- 좌표·이름·장소 링크(`place_url`) 중 하나라도 없는 문서는 결과에서 뺀다. 빈 문자열 주소·전화는 null.
- 같은 `id` 는 한 번만 넣는다.

### 실패

| 상황 | 결과 |
|---|---|
| 위경도 누락·범위 밖, 반경 0 또는 20000 초과 | `INVALID_INPUT` (외부 호출 없음) |
| `KAKAO_REST_API_KEY` 없음 | `MISSING_API_KEY` (외부 호출 없음) |
| 반경 내 카페 0건 | `NO_RESULT` |
| 응답 시간 초과 | `TIMEOUT` |
| 401/403(키 오류), 429(한도 초과), 5xx, JSON/구조 오류 | `API_ERROR` |

## 6. Tool 연결 (앞 Tool 출력 → 다음 Tool 입력)

```
search_restaurant_candidates(area, food_type?, reference_date?, max_results?)
   └─ candidates[i].source, candidates[i].source_id ──▶ get_restaurant_details(source, source_id)
   └─ candidates[i].latitude, candidates[i].longitude ─▶ search_nearby_cafes(latitude, longitude, radius_m?)
```
