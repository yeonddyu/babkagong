# Codex 독립 검증 요청서 — 밥카공 (2차)

- 대상 커밋 범위: `2d2b51d..9080721` (39개, main, GitHub `yeonddyu/babkagong` 와 동일)
- 작성: Claude Code (구현 담당), 2026-11-20. **아래 기대값·PASS 는 모두 구현자 자체 판정이며, 이 문서의 목적은 그 주장을 독립적으로 확인·반박하는 것이다.**
- 1차 요청서(`2d2b51d` 기준)는 git 이력에 있다: `git show 9080721:docs/codex_review_brief.md`

아래 블록을 Codex 에 그대로 전달한다.

```text
너는 밥카공 저장소(/Users/yeondyu/Desktop/AI_PJT_03, GitHub yeonddyu/babkagong main)의 독립 검증자다.
구현은 Claude Code가 했고, 문서(PLAN.md, docs/*, 커밋 메시지)에 적힌 PASS는 모두 구현자의 자체 판정이다.
그 주장을 근거로 삼지 말고, 코드·테스트·실행 결과로 직접 확인하거나 반박해라.

[검증 대상]
- 커밋 범위: 2d2b51d..9080721 (39개). 이전 검증은 2d2b51d까지였다.
- 최상위 기준: 저장소 루트의 AI코어프로젝트_3회차_요구사항정의서.pdf (대외비, gitignore) — F3001~F3019, NF3001~NF3007.
- 주의: AGENTS.md는 서비스 범위를 "강남역·역삼역 일대"라고 적고 있지만, 사용자 요청으로 현재 범위는
  "역삼역(SSAFY) 주변 6개 역: 역삼·강남·언주·신논현·선릉·선정릉"이다. 이 범위 변경이 요구사항정의서와
  충돌하는지도 판단해라 (변경 사유: README.md, docs/implementation_report.md 13장).

[규칙]
1. 읽기 전용. 코드·문서·.env·data/를 수정하지 말고, 커밋·push하지 마라.
2. .env의 키 값을 출력하거나 보고서에 쓰지 마라 (존재 여부만).
3. 서울관광재단(레드테이블) API는 2026-11-20에 호출 한도(HTTP 429)에 걸렸다. scripts.build_cache는 실행하지 마라
   (API 전체를 다시 훑는다). backend/data/cache/의 기존 데이터를 그대로 써라.
4. 실제 외부 API를 부르는 검사(-m integration, scripts.run_scenarios)는 필요한 만큼만 실행해라.
5. 각 항목을 PASS / FAIL / BLOCKED(외부 의존성으로 확인 불가)로 판정하고,
   FAIL은 파일:줄, 재현 방법, 기대 동작을 적어라. 실행하지 않은 것은 PASS로 적지 마라.

[실행] (기대값은 구현자 주장)
cd backend && ../.venv/bin/python -m pytest -q                      # 기대: 280 passed
cd backend && ../.venv/bin/python -m pytest -m integration -rs      # 기대: 18개 중 레드테이블 직접 호출 3개는 429면 BLOCKED
.venv/bin/python backend/scripts/check_secrets.py                   # 기대: 키가 포함된 파일 없음
cd frontend && npx vitest run && npm run build                      # 기대: 84 passed, 빌드 성공
수동 확인: cd backend && ../.venv/bin/uvicorn app.main:app --port 8000 / cd frontend && npm run dev
(카카오 지도는 http://localhost:5173 에서만 동작, 127.0.0.1은 도메인 미등록)

[중점 확인 항목]
A. 데이터 정직성 (CLAUDE.md 규칙)
 - 가격·영업시간·거리·편의시설을 지어내지 않는지 (확인 안 된 값은 null / "확인 필요").
 - 서로 다른 출처 ID를 같은 장소로 연결하지 않는지 (레드테이블·인허가·카카오).
 - 응답의 summary(respond.py _summary)가 확정 값만 쓰는지.
B. 추천 다양성 (a06c5e5, 3787ac3)
 - search_restaurant_candidates의 order=varied·seed: 같은 seed는 같은 결과, 거리 구간별 분포, 메뉴 있는 곳 우선.
 - "많이 걷기 싫어" 요청은 가까운 순 유지, "도보 N분"·"Nm 이내"는 검색 반경(radius_m)으로 바뀌는지.
 - 충족 후보가 1~4곳이면 남은 후보를 이어서 확인하는지 (graph.py execute), 0곳이면 기존 재계획 흐름인지.
C. 출구 기준 (a029328, 9bbc135)
 - "N번 출구"는 규칙(analysis.parse_exit)으로만 추출되는지, LLM 값이 섞이지 않는지.
 - 카카오 키워드 결과 중 분류 '지하철출구'·이름 정확 일치 1곳만 채택하는지 (datasets/exits.py match_exit).
 - 없는 출구는 역 중심으로 찾고 notices에 안내하는지, 거리·판정·요약·지도가 같은 기준점(origin)을 쓰는지.
D. 서비스 역 6곳 (33a9f96, 68ae3c8, 90e8f47, cc94fdf)
 - datasets/stations.py 좌표·역 이름 인식 (신논현/논현, 선정릉/선릉 혼동 없음, "강남"·"역삼" 단독 인식 유지).
 - 서비스 역이 아닌 역(예: 홍대입구역)은 clarify와 "서비스 지역이 아니에요" 안내가 나오는지.
 - 버튼으로 고른 역(area_hint)이 메시지에 역 이름이 없을 때 이전 대화의 역보다 우선하는지,
   메시지에 역 이름이 있으면 메시지가 우선하는지.
 - 인접 지역 재계획이 가까운 순으로 아직 찾지 않은 역으로 가는지.
E. 저장소·성능
 - datasets/sqlite_store.py: 임시 파일에 쓴 뒤 교체, TTL, 동시 빌드 잠금, SQL 변수 개수 분할.
 - 서비스 지역 데이터: 식당 12,994곳·메뉴 66,309행. 같은 날 받은 서울 전역 수집본에서 추려 만들었고
   fetched_at은 원본 시각이라고 주장함 — 메타데이터로 확인.
 - 인사·도움말처럼 Tool이 필요 없는 요청에서 외부 호출이 0회인지.
F. 화면 (UI-01~UI-04 등)
 - 45:55 레이아웃·sticky 지도, 모바일 대화·지도 탭, 지도 정보 카드·카페 바꾸기·저장 시 고른 카페 반영,
   원형 룰렛(바늘 칸 = 결과, 실제 메뉴만), 날씨 마스코트("비 예보" / "비 올 수도" 구분, 실측 아님 표시).
 - 역 칩 6개 한 줄 배치(좁은 화면 3×2)와 "역 이름 없이 보내면 ○○역 주변에서 찾아요" 안내.
 - 역 칩을 누르면 첫 화면 예시 질문 4개가 그 역 이름으로 바뀌고, 누르면 그 문장과 그 역(area)이 그대로 전송되는지 (9080721).
 - prefers-reduced-motion, 키보드 접근, formatMessage의 HTML 이스케이프(XSS).

[구현자가 이미 밝힌 문제 — 사실인지 확인]
 - b999e6d 커밋에 frontend/src/components/WeatherStrip.vue 삭제가 섞여 그 커밋 시점에만 프론트 빌드가 깨짐 (다음 커밋 6a88cb5에서 해결).
 - 8f19e1c 커밋 메시지의 테스트 수 오기 ("ui02-roulette 7개" → 실제 6개).
 - 레드테이블 직접 호출 integration 3개는 429로 BLOCKED.
 - 강남구 밖 역(신논현 일부 등)은 보완 출처(강남구 인허가)가 없음.

[보고 형식]
1) 실행 결과 표 (명령, 결과, 판정)
2) A~F 항목별 PASS / FAIL / BLOCKED와 근거 (파일:줄)
3) 발견한 결함 목록 (심각도 순, 재현 방법·기대 동작)
4) 요구사항정의서 대비 위험 (범위 변경 포함)
5) 구현자 주장 중 확인되지 않은 것
```

## 참고
- `backend/data/cache/` 는 git 에 없다. 이 컴퓨터에서 Codex 를 실행해야 같은 데이터로 검증된다.
- 레드테이블 호출 한도가 풀린 뒤(보통 다음 날) integration 을 다시 실행하면 BLOCKED 3개의 실제 결과를 얻을 수 있다.
