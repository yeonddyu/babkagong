# 외부 API 실제 연결 검증 기록 (NF3007)

- 최종 검증: 2026-11-19 14:40 KST (1차 기록 2026-11-18 은 키 미발급으로 대부분 BLOCKED 였음)
- 명령: `cd backend && ../.venv/bin/python -m scripts.verify_apis`, `../.venv/bin/python -m pytest -m integration -v -rs`
- 비밀키는 URL·로그·문서에 기록하지 않는다 (`serviceKey=***`). `scripts/check_secrets.py` 로 저장소에 키가 없음을 확인.
- **Mock 단위 테스트 통과는 아래 실제 호출 결과와 별개다.**

## 1. 결과 요약

| 제공처 / API | 요청 URL (키 마스킹) | HTTP | 결과 |
|---|---|---|---|
| 서울관광재단 식당기본정보 | `https://seoul.openapi.redtable.global/api/rstr?serviceKey=***&pageNo=1` | 200 | **PASS** — resultCode 00, totalCount 167,659, 1,000행 |
| 서울관광재단 메뉴정보 한국어 | `.../api/menu/korean?serviceKey=***&pageNo=1` | 200 | **PASS** — totalCount 573,965 |
| 서울관광재단 식당운영정보 | `.../api/rstr/oprt?serviceKey=***&pageNo=1` | 200 | **PASS** — totalCount 167,659 |
| 서울관광재단 (잘못된 키) | `.../api/rstr?serviceKey=***` | 401 | PASS — `resultCode 30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR` → `API_ERROR` |
| 서울 열린데이터광장 강남구 일반음식점 `LOCALDATA_072404_GN` | `http://openapi.seoul.go.kr:8088/***/json/LOCALDATA_072404_GN/1/1000/` | 200 | **PASS** — INFO-000, 51,509건 |
| 서울 열린데이터광장 강남구 휴게음식점 `LOCALDATA_072405_GN` | `.../***/json/LOCALDATA_072405_GN/1/5/` | 200 | **PASS** — INFO-000, 17,555건 |
| 기상청 단기예보 `getVilageFcst` | `https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst?serviceKey=***&...&nx=61&ny=125` | 200 | **PASS** — resultCode 00, 798건(1발표) |
| 카카오 로컬 카테고리 검색 CE7 | `https://dapi.kakao.com/v2/local/search/category.json?category_group_code=CE7&x=127.027619&y=37.497952&radius=300` | 403 | **BLOCKED** — `NotAuthorizedError: App(밥카공) disabled OPEN_MAP_AND_LOCAL service` (키는 유효, 앱에서 카카오맵 사용 설정 필요) |
| 카카오 (잘못된 키) | 위와 동일 | 401 | PASS — `AccessDeniedError` → `API_ERROR` |
| OpenAI | - | - | **BLOCKED** — `OPENAI_API_KEY` 미설정. 요청 분석·응답 문장은 규칙/템플릿 경로로 동작 |
| SSAFY GMS | - | - | **EXCLUDED** — `GMS_API_KEY` 존재 확인만, 모델 연동은 이번 범위 밖 |

데이터 API 3종 이상 확보 조건: 서울관광재단·서울 열린데이터광장·기상청 3개 제공처가 **실제 호출로 확인됨 (충족)**. 카카오가 활성화되면 4종.

통합 테스트 (`pytest -m integration -v -rs`, 2026-11-19): **13 passed, 2 skipped** — skip 2건은 카카오 403 으로 BLOCKED.

## 2. 제공처별 상세

### 2.1 서울관광재단 음식관광 데이터베이스 OPEN API (레드테이블)
| 항목 | 내용 |
|---|---|
| 출처 | 공공데이터포털 https://www.data.go.kr/data/15097605/openapi.do (LINK 유형) → https://seoul.openapi.redtable.global |
| 인증 | `serviceKey` 쿼리 파라미터 (레드테이블 토큰) — 환경변수 `REDTABLE_API_KEY` |
| 파라미터 | `serviceKey`, `pageNo` 뿐. **지역·식당ID 필터 없음**, 페이지당 1,000건 |
| 사용 필드 | 기본 `RSTR_ID, RSTR_NM, RSTR_RDNMADR, RSTR_LNNO_ADRES, RSTR_LA, RSTR_LO, RSTR_TELNO, BSNS_STATM_BZCND_NM, BSNS_LCNC_NM` / 메뉴 `MENU_ID, MENU_NM, MENU_PRICE, SPCLT_MENU_YN, RSTR_ID` / 운영 `BSNS_TM_CN, RESTDY_INFO_CN, WIFI_OFR_YN, PRKG_POS_YN, SEAT_CNT, ...` |
| 실데이터 특성 | 강남·역삼 1.5km 내 식당 8,125곳 중 메뉴 등록 1,560곳, 영업시간 등록 3,450곳. 같은 메뉴 중복 행(87곳), 1원 같은 비정상 가격 존재 → 중복 제거·식사 메뉴 판정 정책 적용 |
| 호출 한도 | 공공데이터포털 표기 "기관 정책에 따라 상이", 정의서상 429(한도 초과) 정의. 수치 미공개 |
| 이용 조건 | 무료, 이용허락범위 제한 없음, 개발단계 자동승인 / 운영단계 심의승인 |
| 수집 비용(실측) | 식당기본정보 168페이지 45초, 운영정보 56초, 메뉴정보 575페이지 217초 |
| 저장·재사용 | 서비스 지역 데이터만 `backend/data/cache/*.json` 에 저장, TTL 168시간 후 재수집 (호출 최소화). 캐시는 저장소에 커밋하지 않음 |

### 2.2 서울 열린데이터광장 — 강남구 일반음식점·휴게음식점 인허가 정보
| 항목 | 내용 |
|---|---|
| 출처 | https://data.seoul.go.kr (원본: 공공데이터포털 지방행정 인허가정보) |
| 요청 | `http://openapi.seoul.go.kr:8088/{KEY}/json/{SERVICE}/{START}/{END}/`, 1회 최대 1,000건 (`sample` 키는 5건) |
| 사용 필드 | `MGTNO`(출처 식별자), `BPLCNM`, `UPTAENM`, `TRDSTATEGBN/TRDSTATENM`, `APVPERMYMD`, `DCBYMD`, `RDNWHLADDR`, `SITEWHLADDR`, `X`,`Y`(EPSG:5174 → WGS84 변환), `UPDATEDT` |
| 오류 형식(실측) | JSON 요청에도 HTTP 200 + XML(`INFO-100` 키 오류, `ERROR-335` 범위 초과) → Client 가 감지해 `API_ERROR` |
| 이용 조건 | 이용허락범위 제한 없음 (데이터셋 표기), 매일 갱신 |
| 용도 | 일반음식점: 음식점 후보 보완·기준일 영업 판정 / 휴게음식점(커피숍·다방 등): 카카오 실패 시 보조 카페 |
| 한계 | 강남구만 포함 → 강남역 서측(서초구) 업소 없음. 메뉴·가격·영업시간 없음 |

### 2.3 기상청 단기예보 조회서비스
| 항목 | 내용 |
|---|---|
| 출처 | 공공데이터포털 https://www.data.go.kr/data/15084084/openapi.do |
| 요청 | `getVilageFcst`, `serviceKey`(인코딩 키, 재인코딩 방지 위해 URL 에 직접 부착), `base_date`, `base_time`(02·05·08·11·14·17·20·23시), `nx`,`ny` (강남·역삼 = 61,125) |
| 사용 필드 | `category`(TMP, POP, PTY, SKY, PCP, REH, WSD), `fcstDate`, `fcstTime`, `fcstValue` |
| 호출 한도 | 개발계정 10,000건/일 (운영계정은 활용사례 등록 시 증가) |
| 이용 조건 | 무료, **공공누리 제1유형(출처표시)** → 화면·문서에 "기상청 단기예보" 출처 표시 |

### 2.4 카카오 로컬 API
| 항목 | 내용 |
|---|---|
| 요청 | `GET /v2/local/search/category.json`, 헤더 `Authorization: KakaoAK {키}`, `category_group_code=CE7`, `x`,`y`,`radius`(≤20000),`page`(≤45),`size`(≤15),`sort=distance` |
| 현재 상태 | 키는 설정되어 있으나 앱 설정에서 카카오맵 서비스 비활성 → 403. **사용자 조치 필요**: 카카오디벨로퍼스 → 내 애플리케이션 → 밥카공 → 카카오맵 사용 설정 ON |
| 호출 한도 | 카카오디벨로퍼스 쿼터 정책(앱 [쿼터] 메뉴), 무료 월간 쿼터는 계정의 첫 활성 앱에 제공 |
| 이용 조건 | 카카오 API 이용약관. 장소 정보는 응답 시점 결과만 표시하고 저장하지 않음 (대화 Memory 에 이름·링크 요약만) |

### 2.5 OpenAI / SSAFY GMS
- OpenAI: `OPENAI_API_KEY` 설정 시 `core/llm_provider.py` 가 ChatOpenAI(`OPENAI_MODEL`, 기본 gpt-4o-mini)를 생성. 현재 키 없음 → BLOCKED.
- GMS: 키 존재만 확인. `AI_PROVIDER=gms` 여도 GMS 를 호출하지 않는다.

## 3. BLOCKED 해제 방법
1. 카카오: 앱에서 카카오맵 사용 설정 → `pytest -m integration -rs` 의 skip 2건이 PASS 로 바뀌는지 확인
2. OpenAI: `.env` 에 `OPENAI_API_KEY` 입력 → `/api/health` 의 `llm.available=true`, 응답의 `decided_by=llm` 확인
3. 갱신 후 `scripts.verify_apis` 결과로 이 문서 1절 갱신
