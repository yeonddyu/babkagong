# DB 스키마 (SQLite, SQLAlchemy)

파일: `backend/data/babkagong.db` (gitignore). 설정: `DATABASE_URL`.

## plans (F3015, F3016)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| title | TEXT | 코스 제목 |
| plan_date | DATE | 방문 날짜 (필수) |
| start_time | TIME | 시작 시각 (필수) |
| end_time | TIME | 종료 시각 (필수, start < end) |
| area | TEXT | 강남역/역삼역 |
| restaurant_name / restaurant_source / restaurant_source_id / restaurant_address | TEXT | 식당 (출처·식별자 보존) |
| cafe_name / cafe_place_id / cafe_address / cafe_url | TEXT | 카페 (선택) |
| restaurant_lat / restaurant_lng / cafe_lat / cafe_lng | REAL | 저장 당시 확인된 좌표 (선택, 저장 코스 지도용). 이전 DB 는 시작 시 `ALTER TABLE ADD COLUMN` 으로 보완 |
| memo | TEXT | |
| session_id | TEXT | 추천을 만든 대화 세션 (선택) |
| created_at / updated_at | DATETIME | KST |

충돌 판정: 같은 `plan_date` 에서 `a.start < b.end AND b.start < a.end` 인 다른 계획. 저장은 막지 않고 응답 `conflicts` 에 반환.

## execution_logs (F3013, F3014)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| session_id | TEXT, index | 세션 단위 구분 |
| run_id | TEXT | 한 번의 요청 실행 |
| seq | INTEGER | 실행 내 발생 순서 |
| event_type | TEXT | stage_start, tool_call, ... |
| stage | TEXT | analyze/plan/execute/judge/replan/respond |
| payload | JSON | 원본 이벤트 내용 (LLM 가공 없음) |
| created_at | DATETIME | 이벤트 발생 시각 |

수정 API 없음 (조회·삭제만).

## sessions (F3010)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| session_id | TEXT PK | |
| memory | JSON | 직전 조건·추천 요약 (원본 API 응답 제외) |
| updated_at | DATETIME | |
