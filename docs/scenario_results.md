# 대표 시나리오 검증 결과 (요구사항정의서 4.7)

- 실행 일시: 2026-11-19 14:36 KST, 명령: `cd backend && ../.venv/bin/python -m scripts.run_scenarios`
- 외부 API: **실제 호출** (서울관광재단·서울 열린데이터광장·기상청). 카카오는 앱의 카카오맵 비활성(HTTP 403)으로 실패 → 휴게음식점 보조 출처 사용
- LLM: 미사용 — OPENAI_API_KEY 없음, 요청 분석·응답 문장은 규칙/템플릿
- 실행 로그 샘플: `docs/samples/run_log_S1_full.json`(대표 요청 1건 전체), `docs/samples/run_log_S3_replan_limit.json`(재계획 사례)
- 변경 이력: 1차 실행에서 S2 요청('강남역 일식 1만 2천원 이하로 12시 점심')은 실제 데이터상 첫 상세조회 묶음에서 충족 후보가 나와 재계획이 발생하지 않음(FAIL, 시나리오 선택 오류 — 코드 결함 아님). 재계획이 실제로 발생하는 요청으로 교체 후 재실행.

| ID | 시나리오 | 결과 | 시간(초) | Tool 호출(신규) | 재계획 | 추천 |
|---|---|---|---|---|---|---|
| S1 | 제약을 한 번에 충족 | PASS | 1.59 | 9 | - | 명가교동짬뽕(역삼역점), 질할브로스(역삼점) |
| S2 | 재계획이 필요한 요청 | PASS | 1.25 | 16 | 1:next_batch | 정통일식 최수사 대게마을, 미네스시 |
| S3 | 재계획 상한 도달 | PASS | 1.12 | 26 | 1:next_batch, 2:next_batch, 3:next_batch | - |
| S4 | Tool 하나가 실패 (카카오 403 실제 실패 + 기상청 키 제거) | PASS | 0.4 | 10 | - | 베트남 쌀국수, 고구마명가(강남역점), 만남의 광장 |
| S5 | Tool 이 필요 없는 요청 (인사) | PASS | 0.0 | 0 | - | - |
| S6 | Tool 이 필요 없는 요청 (사용법) | PASS | 0.0 | 0 | - | - |
| S7 | 날씨 반영 + 도보 선호 | PASS | 1.26 | 10 | - | 베트남 쌀국수, 고구마명가(강남역점), 만남의 광장 |
| S8 | 후속 요청 맥락 유지 | PASS | 1.25 | 16 | 1:next_batch | 정통일식 최수사 대게마을, 미네스시 |
| S9 | 계획 저장 (Tool 아님) | PASS | 0.01 | 0 | - | - |
| S10 | 같은 시간대 두 번째 저장 → 충돌 안내 | PASS | 0.01 | 0 | - | - |

## S1. 제약을 한 번에 충족

- 요청: "역삼역에서 1만 5천원 이하로 12시에 점심 먹고 카공할래" (세션 S1)
- 기대 동작: 재계획 없이 예산 이하 메뉴가 확인된 식당 + 주변 카페 추천
- 판정 기준: 추천 있음·재계획 없음 → **PASS**
- 단계: analyze → plan → execute → judge → respond
- Tool 호출: get_weather_context:ok, search_restaurant_candidates:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, search_nearby_cafes:ok, search_nearby_cafes(재사용):ok
- 재계획: 없음
- 제외 후보 수: 4, 안내: 없음
- 최종 응답:

```
🌤 11-19 12:00 예보: 4.0°C, 강수확률 30% (없음)
조건에 맞는 코스 2개를 찾았어요.
1. 명가교동짬뽕(역삼역점) — 역에서 직선 48m(도보 약 1분 추정), 메뉴 예: 쟁반짜장 15,000원, 발사믹크림찹쌀탕수육(사천찹쌀/小) 15,000원, 영업 평일 10:30~22:00, 공휴일 11:00~20:30
   ☕ 식당에서 직선 57m: 매머드익스프레스 역삼역5번출구점
2. 질할브로스(역삼점) — 역에서 직선 48m(도보 약 1분 추정), 메뉴 예: 램 오버 라이스 7,900원, 콤보 라이스(치킨+램) 7,900원, 영업 평일 10:30~21:00, 주말 11:00~20:00
   ☕ 식당에서 직선 57m: 매머드익스프레스 역삼역5번출구점
카페 영업시간·콘센트·와이파이·혼잡도는 외부 데이터로 확인할 수 없어 방문 전 확인이 필요합니다.
```

- 기대와 차이: 없음

## S2. 재계획이 필요한 요청

- 요청: "역삼역에서 일식 1만 5천원 이하로 12시 점심" (세션 S2)
- 기대 동작: 첫 상세조회 묶음에서 충족 0건 → 다음 묶음(또는 인접 역) 재계획 후 추천, 이미 호출한 Tool 재호출 없음
- 판정 기준: 재계획 발생·중복 호출 없음 → **PASS**
- 단계: analyze → plan → execute → judge → replan → execute → judge → respond
- Tool 호출: get_weather_context:ok, search_restaurant_candidates:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, search_nearby_cafes:ok, search_nearby_cafes:ok
- 재계획: 1:next_batch
- 제외 후보 수: 10, 안내: 없음
- 최종 응답:

```
🌤 11-19 12:00 예보: 4.0°C, 강수확률 30% (없음)
조건에 맞는 코스 2개를 찾았어요.
1. 정통일식 최수사 대게마을 — 역에서 직선 186m(도보 약 4분 추정), 메뉴 예: 어린이 정식 15,000원, 알밥 15,000원, 영업 매일 11:00~22:30
   ☕ 식당에서 직선 2m: 메가엠지씨커피 역삼GFC점
2. 미네스시 — 역에서 직선 212m(도보 약 5분 추정), 메뉴 예: 청하 10,000원, 아사히 10,000원, 영업 매일 11:30~22:30
   ☕ 식당에서 직선 63m: 데어 무트(der Mut)
카페 영업시간·콘센트·와이파이·혼잡도는 외부 데이터로 확인할 수 없어 방문 전 확인이 필요합니다.
```

- 기대와 차이: 없음

## S3. 재계획 상한 도달

- 요청: "역삼역 1천원 이하 점심" (세션 S3)
- 기대 동작: 재계획 3회 후 중단, 사유와 조건 조정 제안
- 판정 기준: 재계획 3회·상한 사유·제안 → **PASS**
- 단계: analyze → plan → execute → judge → replan → execute → judge → replan → execute → judge → replan → execute → judge → respond
- Tool 호출: get_weather_context:ok, search_restaurant_candidates:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok
- 재계획: 1:next_batch, 2:next_batch, 3:next_batch / 중단 사유: 재계획 상한(3회)에 도달
- 제외 후보 수: 24, 안내: 없음
- 최종 응답:

```
🌤 11-19 12:00 예보: 4.0°C, 강수확률 30% (없음)
조건을 모두 만족하는 식당을 찾지 못했어요.
사유: 재계획 상한(3회)에 도달
제외한 예: 누들톡(역삼역점)(예산 판단 불가: 가격 미확인 — 1,000원 이하 메뉴가 있는지 매장에서 확인 필요); 다미분식(예산 판단 불가: 가격 미확인 — 1,000원 이하 메뉴가 있는지 매장에서 확인 필요); 만권화밥(역삼점)(예산 판단 불가: 가격 미확인 — 1,000원 이하 메뉴가 있는지 매장에서 확인 필요)
이렇게 바꿔 보시겠어요? 예산을 6,000원 정도로 올려 보기 / 가격·영업시간이 확인된 식당이 적어서, 조건을 줄이면 더 많은 후보를 판단할 수 있어요
```

- 기대와 차이: 없음

## S4. Tool 하나가 실패 (카카오 403 실제 실패 + 기상청 키 제거)

- 요청: "강남역 점심 먹고 카공할 곳 추천해줘" (세션 S4)
- 기대 동작: 날씨 Tool MISSING_API_KEY·카카오 실패에도 나머지 단계 진행, 안내 표시, 추천 제공
- 판정 기준: 실패 Tool 존재·추천 계속·안내 → **PASS**
- 단계: analyze → plan → execute → judge → respond
- Tool 호출: get_weather_context:MISSING_API_KEY, search_restaurant_candidates:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, search_nearby_cafes:ok, search_nearby_cafes(재사용):ok, search_nearby_cafes:ok
- 재계획: 없음
- 제외 후보 수: 1, 안내: 날씨 조회: API 키가 설정되지 않아 확인하지 못했습니다
- 최종 응답:

```
조건에 맞는 코스 3개를 찾았어요.
1. 베트남 쌀국수 — 역에서 직선 65m(도보 약 2분 추정), 영업 평일 09:00~21:00, 토요일 09:00~21:00
   ☕ 식당에서 직선 46m: 스타벅스 강남R점
2. 고구마명가(강남역점) — 역에서 직선 65m(도보 약 2분 추정)
   ☕ 식당에서 직선 46m: 스타벅스 강남R점
   ⚠ 영업시간 미확인 — 12:00 영업 여부를 방문 전 확인 필요
3. 만남의 광장 — 역에서 직선 50m(도보 약 1분 추정)
   ☕ 식당에서 직선 93m: 빽다방
   ⚠ 영업시간 미확인 — 12:00 영업 여부를 방문 전 확인 필요
카페 영업시간·콘센트·와이파이·혼잡도는 외부 데이터로 확인할 수 없어 방문 전 확인이 필요합니다.
ℹ 날씨 조회: API 키가 설정되지 않아 확인하지 못했습니다
```

- 기대와 차이: 없음

## S5. Tool 이 필요 없는 요청 (인사)

- 요청: "안녕!" (세션 S5)
- 기대 동작: 계획 생략, Tool 호출 0회
- 판정 기준: Tool 0회·plan 단계 없음 → **PASS**
- 단계: analyze → respond
- Tool 호출: 없음
- 재계획: 없음
- 제외 후보 수: 0, 안내: 없음
- 최종 응답:

```
안녕하세요! 밥카공이에요. 강남역·역삼역에서 식사하고 카공할 곳을 함께 추천해 드릴게요. 어디서 무엇을 드시고 싶은지 말씀해 주세요.
```

- 기대와 차이: 없음

## S6. Tool 이 필요 없는 요청 (사용법)

- 요청: "사용법 알려줘" (세션 S6)
- 기대 동작: 사용법 안내, Tool 호출 0회
- 판정 기준: Tool 0회 → **PASS**
- 단계: analyze → respond
- Tool 호출: 없음
- 재계획: 없음
- 제외 후보 수: 0, 안내: 없음
- 최종 응답:

```
밥카공은 강남역·역삼역 주변에서 식사할 곳과 식사 후 카공할 카페를 함께 추천해요.
• 예: "강남역에서 1만 5천원 이하로 12시에 점심 먹고 카공할래"
• 조건: 날짜·시각, 음식 종류, 예산, 가까운 곳 선호, 몇 m/몇 분 이내
• 후속: "같은 조건에서 한식 말고 일식으로", "이 코스로 저장해줘"
메뉴 가격·영업시간은 서울관광재단 데이터로 확인된 경우만 사용하고, 날씨는 기상청 예보를 반영해요.
```

- 기대와 차이: 없음

## S7. 날씨 반영 + 도보 선호

- 요청: "오늘 비가 오는데 강남역에서 점심 먹고 카공하고 싶어. 많이 걷기는 싫어." (세션 S7)
- 기대 동작: 기상청 예보 조회, 가까운 곳 선호 반영(카페 반경 300m), 말한 날씨와 예보가 다르면 안내
- 판정 기준: 날씨 조회 성공·카페 반경 300m → **PASS**
- 단계: analyze → plan → execute → judge → respond
- Tool 호출: get_weather_context:ok, search_restaurant_candidates:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, search_nearby_cafes:ok, search_nearby_cafes(재사용):ok, search_nearby_cafes:ok
- 재계획: 없음
- 제외 후보 수: 1, 안내: 말씀하신 날씨(비)와 달리 기상청 예보는 강수확률 30%·없음예요. 가까운 곳 선호는 그대로 반영했어요.
- 최종 응답:

```
🌤 11-19 12:00 예보: 4.0°C, 강수확률 30% (없음)
조건에 맞는 코스 3개를 찾았어요.
1. 베트남 쌀국수 — 역에서 직선 65m(도보 약 2분 추정), 영업 평일 09:00~21:00, 토요일 09:00~21:00
   ☕ 식당에서 직선 46m: 스타벅스 강남R점
2. 고구마명가(강남역점) — 역에서 직선 65m(도보 약 2분 추정)
   ☕ 식당에서 직선 46m: 스타벅스 강남R점
   ⚠ 영업시간 미확인 — 12:00 영업 여부를 방문 전 확인 필요
3. 만남의 광장 — 역에서 직선 50m(도보 약 1분 추정)
   ☕ 식당에서 직선 93m: 빽다방
   ⚠ 영업시간 미확인 — 12:00 영업 여부를 방문 전 확인 필요
카페 영업시간·콘센트·와이파이·혼잡도는 외부 데이터로 확인할 수 없어 방문 전 확인이 필요합니다.
ℹ 말씀하신 날씨(비)와 달리 기상청 예보는 강수확률 30%·없음예요. 가까운 곳 선호는 그대로 반영했어요.
```

- 기대와 차이: 없음

## S8. 후속 요청 맥락 유지

- 요청: "같은 조건에서 한식 말고 일식으로 바꿔줘" (세션 S1)
- 기대 동작: S1 의 지역·예산·시각 유지, 음식 종류만 일식으로 변경
- 판정 기준: 변경 필드만 갱신 → **PASS**
- 단계: analyze → plan → execute → judge → replan → execute → judge → respond
- Tool 호출: get_weather_context:ok, search_restaurant_candidates:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, get_restaurant_details:ok, search_nearby_cafes:ok, search_nearby_cafes:ok
- 재계획: 1:next_batch
- 제외 후보 수: 10, 안내: 없음
- 최종 응답:

```
🌤 11-19 12:00 예보: 4.0°C, 강수확률 30% (없음)
조건에 맞는 코스 2개를 찾았어요.
1. 정통일식 최수사 대게마을 — 역에서 직선 186m(도보 약 4분 추정), 메뉴 예: 어린이 정식 15,000원, 알밥 15,000원, 영업 매일 11:00~22:30
   ☕ 식당에서 직선 2m: 메가엠지씨커피 역삼GFC점
2. 미네스시 — 역에서 직선 212m(도보 약 5분 추정), 메뉴 예: 청하 10,000원, 아사히 10,000원, 영업 매일 11:30~22:30
   ☕ 식당에서 직선 63m: 데어 무트(der Mut)
카페 영업시간·콘센트·와이파이·혼잡도는 외부 데이터로 확인할 수 없어 방문 전 확인이 필요합니다.
```

- 기대와 차이: 없음

## S9. 계획 저장 (Tool 아님)

- 요청: "이 코스로 저장해줘" (세션 S1)
- 기대 동작: 직전 추천 1번을 날짜·시각과 함께 저장, Tool 호출 0회
- 판정 기준: 저장됨·Tool 0회 → **PASS**
- 단계: analyze → save → respond
- Tool 호출: 없음
- 재계획: 없음
- 제외 후보 수: 0, 안내: 없음
- 최종 응답:

```
계획을 저장했어요: 정통일식 최수사 대게마을 + 메가엠지씨커피 역삼GFC점 — 2026-11-19 12:00~15:00
ℹ 날짜를 말하지 않아 오늘(2026-11-19)로 저장했어요.
ℹ 종료 시각은 식사 60분 + 카공 120분 기준 15:00로 저장했어요. 계획 화면에서 수정할 수 있어요.
```

- 기대와 차이: 없음

## S10. 같은 시간대 두 번째 저장 → 충돌 안내

- 요청: "2번 코스도 저장해줘" (세션 S1)
- 기대 동작: 저장은 되고 겹치는 계획을 함께 안내
- 판정 기준: 저장됨·충돌 안내 → **PASS**
- 단계: analyze → save → respond
- Tool 호출: 없음
- 재계획: 없음
- 제외 후보 수: 0, 안내: 없음
- 최종 응답:

```
계획을 저장했어요: 미네스시 + 데어 무트(der Mut) — 2026-11-19 12:00~15:00
ℹ 날짜를 말하지 않아 오늘(2026-11-19)로 저장했어요.
ℹ 종료 시각은 식사 60분 + 카공 120분 기준 15:00로 저장했어요. 계획 화면에서 수정할 수 있어요.
⚠ 같은 날 시간이 겹치는 계획이 있어요 (저장은 완료): 정통일식 최수사 대게마을 + 메가엠지씨커피 역삼GFC점(12:00~15:00)
```

- 기대와 차이: 없음
