# 외부 API 실제 연결 검증 기록

- 검증 일시: 2026-11-18 17:16 KST
- 검증 명령: `.venv/bin/python -m scripts.verify_apis`, `.venv/bin/python -m pytest -m integration -v -rs`
- 검증 환경: `.env` 없음 → `REDTABLE_API_KEY`, `SEOUL_OPENAPI_KEY`, `KAKAO_REST_API_KEY` **모두 미설정**
- 비밀키는 URL·로그·보고서에 기록하지 않는다 (`serviceKey=***`).

> **요약**: 개인 키가 없어 정상 데이터 호출로 검증할 수 있었던 것은 서울 열린데이터광장 공개 `sample` 키(최대 5건) 1건뿐이다.
> 레드테이블·카카오는 **잘못된 키에 대한 실제 거부 응답(401)** 만 확인했고, 정상 응답 검증은 **BLOCKED** 이다.
> Mock 단위 테스트 통과를 실제 API 호출 성공으로 간주하지 않는다.

## 1. 결과 요약

| # | 제공처 / API | 요청 URL | HTTP | 결과 |
|---|---|---|---|---|
| 1 | 서울관광재단 식당기본정보 | `https://seoul.openapi.redtable.global/api/rstr?serviceKey=***&pageNo=1` | - | **BLOCKED** (키 없음) |
| 2 | 서울관광재단 메뉴정보 한국어 | `https://seoul.openapi.redtable.global/api/menu/korean?serviceKey=***&pageNo=1` | - | **BLOCKED** (키 없음) |
| 3 | 서울관광재단 식당운영정보 | `https://seoul.openapi.redtable.global/api/rstr/oprt?serviceKey=***&pageNo=1` | - | **BLOCKED** (키 없음) |
| 4 | 서울관광재단 식당기본정보 (잘못된 키) | `https://seoul.openapi.redtable.global/api/rstr?serviceKey=***&pageNo=1` | 401 | PASS — `{"resultCode":"30","resultMsg":"SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}` 확인, Client 가 `API_ERROR` 로 변환 |
| 5 | 서울 열린데이터광장 `LOCALDATA_072404_GN` (공개 sample 키) | `http://openapi.seoul.go.kr:8088/sample/json/LOCALDATA_072404_GN/1/5/` | 200 | **PASS** — `INFO-000`, `list_total_count=51509`, 5행 |
| 6 | 서울 열린데이터광장 `LOCALDATA_072404_GN` (개인 키 1~1000건) | `http://openapi.seoul.go.kr:8088/***/json/LOCALDATA_072404_GN/1/1000/` | - | **BLOCKED** (키 없음) |
| 7 | 카카오 로컬 카테고리 검색 CE7 | `https://dapi.kakao.com/v2/local/search/category.json?category_group_code=CE7&x=127.027619&y=37.497952&radius=300&sort=distance&size=15` | - | **BLOCKED** (키 없음) |
| 8 | 카카오 로컬 (잘못된 키) | 위와 동일, `Authorization: KakaoAK ***` | 401 | PASS — `errorType=AccessDeniedError` 확인, Client 가 `API_ERROR` 로 변환 |

통합 테스트 (`pytest -m integration -v -rs`): **4 passed, 8 skipped(BLOCKED)**

| 테스트 | 결과 |
|---|---|
| `test_live_f3002::test_seoul_opendata_public_sample_key` | PASSED (실제 응답 정규화·좌표 변환 확인) |
| `test_live_f3002::test_seoul_opendata_sample_key_limit_is_reported` | PASSED (6건 요청 → `ERROR-335` → `API_ERROR`) |
| `test_live_f3002::test_redtable_invalid_key_rejected` | PASSED |
| `test_live_f3004::test_kakao_invalid_key_rejected` | PASSED |
| `test_live_f3002::test_seoul_opendata_personal_key` | SKIPPED — BLOCKED |
| `test_live_f3002::test_redtable_restaurant_first_page` | SKIPPED — BLOCKED |
| `test_live_f3002::test_search_restaurant_candidates_live` | SKIPPED — BLOCKED |
| `test_live_f3003::test_redtable_detail_endpoints_first_page` ×2 | SKIPPED — BLOCKED |
| `test_live_f3003::test_candidate_to_details_live` | SKIPPED — BLOCKED |
| `test_live_f3004::test_search_nearby_cafes_live` | SKIPPED — BLOCKED |
| `test_live_f3004::test_search_nearby_cafes_live_no_result` | SKIPPED — BLOCKED |

## 2. 제공처별 상세

### 2.1 서울관광재단 음식관광 데이터베이스 OPEN API (레드테이블)

| 항목 | 내용 |
|---|---|
| 정식 명칭 | 서울관광재단_포스트코로나 이후의 관광객에게 현행화된 정보를 제공하기 위한 음식관광 데이터베이스 OPEN API |
| 공공데이터포털 | https://www.data.go.kr/data/15097605/openapi.do (API 유형: LINK) |
| 키 발급 | https://seoul.openapi.redtable.global → API TOKEN 발급신청 |
| 서비스 URL | `https://seoul.openapi.redtable.global` |
| 인증 | `serviceKey` 쿼리 파라미터 (URL Encode) |
| 요청 파라미터 | `serviceKey`(필수), `pageNo`(선택) — **지역·식당ID 필터 없음** (정의서 기준) |
| 사용 엔드포인트 | `/api/rstr` 식당기본정보, `/api/menu/korean` 메뉴정보 한국어, `/api/rstr/oprt` 식당운영정보 |
| 응답 형식 | `{"header": {resultCode, resultMsg, numOfRows, pageNo, totalCount}, "body": [...]}` |
| 주요 필드 (정의서) | 기본: `RSTR_ID, RSTR_NM, RSTR_RDNMADR, RSTR_LNNO_ADRES, RSTR_LA, RSTR_LO, RSTR_TELNO, BSNS_STATM_BZCND_NM, BSNS_LCNC_NM` / 메뉴: `MENU_ID, MENU_NM, MENU_PRICE, SPCLT_MENU_YN, RSTR_ID` / 운영: `BSNS_TM_CN, RESTDY_INFO_CN, WIFI_OFR_YN, PRKG_POS_YN, SEAT_CNT, ...` |
| 데이터 규모 (정의서 예시) | 식당기본정보 168,155건, 메뉴정보 한국어 574,019건, 페이지당 1,000건 |
| HTTP 상태 (정의서) | 200 성공, 400 파라미터 오류, 401 인증 오류, 404 미정의 API, 429 사용량/초당 한도 초과, 500/502 시스템 오류, 503 점검 |
| 호출 한도 | 공공데이터포털 표기: “해당 기관의 정책에 따라 트래픽 수는 상이”. 정의서에 429(한도 초과) 정의. **구체 수치 미공개 → 키 발급 후 확인 필요** |
| 이용 조건 | 무료, 이용허락범위 제한 없음, 개발단계 자동승인 / 운영단계 심의승인 (공공데이터포털 표기) |
| 실제 확인 | 잘못된 키 → HTTP 401, `resultCode=30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR`. 정상 응답 **미확인(BLOCKED)** |
| 구현 대응 | 필터가 없어 전체 페이지 순회 후 강남·역삼 1.5km 데이터만 `data/cache/` 에 캐시(TTL 168h)해 호출 수를 줄임 |

### 2.2 서울 열린데이터광장 — 강남구 일반음식점 인허가 정보

| 항목 | 내용 |
|---|---|
| 서비스명 | `LOCALDATA_072404_GN` |
| 키 발급 | https://data.seoul.go.kr → 인증키 신청 |
| 요청 URL 형식 | `http://openapi.seoul.go.kr:8088/{KEY}/json/LOCALDATA_072404_GN/{START}/{END}/` |
| 호출 한도 | 1회 최대 1,000건(구현 기준). 공개 `sample` 키는 1~5건만 허용 — 6건 요청 시 `ERROR-335` 실제 확인. 일일 한도 수치는 **미확인** |
| 실제 응답 | HTTP 200, `RESULT.CODE=INFO-000`, `list_total_count=51509` |
| 주요 필드 (실제 응답) | `MGTNO`(관리번호, 출처 식별자), `BPLCNM`(사업장명), `UPTAENM`(업태), `TRDSTATEGBN/TRDSTATENM`(영업상태), `APVPERMYMD`(인허가일), `DCBYMD`(폐업일), `RDNWHLADDR`(도로명주소), `SITEWHLADDR`(지번주소), `X`,`Y`(EPSG:5174 TM 좌표), `UPDATEDT` 등 39개 |
| 오류 형식 (실제 확인) | JSON 요청이어도 HTTP 200 + XML `<RESULT><CODE>INFO-100</CODE>` (잘못된 키), `ERROR-335` (sample 범위 초과) → Client 가 XML 을 감지해 `API_ERROR` 로 변환 |
| 좌표 | `X`,`Y` 는 EPSG:5174 로 보고 WGS84 변환. 실제 행 `삼성로 306` → (37.4994, 127.0609) 로 변환되어 위치가 일치 |
| 이용 조건 | 서울 열린데이터광장 이용약관 및 공공누리 표시 조건 준수 (데이터셋별 공공누리 유형은 데이터셋 페이지에서 확인 필요) |
| 한계 | 강남구 데이터만 포함 → 강남역 서측(서초구) 업소 없음. 메뉴·가격·영업시간 없음 |

### 2.3 카카오 로컬 API — 카테고리로 장소 검색

| 항목 | 내용 |
|---|---|
| 요청 URL | `GET https://dapi.kakao.com/v2/local/search/category.json` |
| 인증 | 헤더 `Authorization: KakaoAK {REST_API_KEY}` |
| 파라미터 | `category_group_code=CE7`(카페), `x`(경도), `y`(위도), `radius`(0~20000m), `page`(1~45), `size`(1~15), `sort=distance` |
| 응답 필드 | `meta{total_count, pageable_count, is_end}`, `documents[]{id, place_name, category_name, phone, address_name, road_address_name, x, y, place_url, distance}` |
| 미제공 정보 | 영업시간·콘센트·와이파이·혼잡도 → Tool 에서 null 로 고정 |
| 호출 한도 | 카카오디벨로퍼스 쿼터 정책 적용(앱 [쿼터] 메뉴에서 확인). 카카오맵 API 무료 쿼터는 계정의 첫 활성화 앱에만 제공. **로컬 API 일 한도 수치는 키 발급 후 앱 설정에서 확인 필요** |
| 실제 확인 | 키 없음 → HTTP 401 `cannot find Authorization : KakaoAK header`, 잘못된 키 → HTTP 401 `AccessDeniedError`. 정상 응답 **미확인(BLOCKED)** |

## 3. BLOCKED 해제 방법

1. 각 제공처에서 키 발급 → `.env` 에 입력 (`.env.example` 참고, `.env` 는 커밋 금지)
2. `.venv/bin/python -m scripts.verify_apis` 실행 후 이 문서의 1·2절 갱신
3. `.venv/bin/python -m pytest -m integration -v -rs` 에서 skip 0건 확인
4. 레드테이블 첫 실행은 식당기본정보 약 169페이지, 메뉴정보 약 575페이지를 순회하므로 시간이 걸린다. 실제 소요 시간과 429 발생 여부를 기록한다.

## 4. 참고 출처

- 공공데이터포털 데이터셋 페이지 및 첨부 `B161_OpenAPI정의서_레드테이블_서울관광재단.pdf`
- 서울 열린데이터광장 OpenAPI 실제 응답 (`sample` 키)
- 카카오디벨로퍼스 쿼터 안내: https://developers.kakao.com/docs/ko/getting-started/quota
