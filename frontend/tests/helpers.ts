// UI 개선 테스트 공용 가짜 데이터 (Mock — 실제 API 응답이 아님)
import { vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import ChatView from '../src/views/ChatView.vue'
import PlansView from '../src/views/PlansView.vue'
import type { ChatResponse, Recommendation } from '../src/types'

export function makeRec(over: Partial<Recommendation> = {}): Recommendation {
  return {
    name: '김치찌개집', source: 'seoul_tourism_redtable', source_id: '1', address: '서울 강남구 테스트로 1', area: '강남역',
    latitude: 37.4981, longitude: 127.0277,
    category: '한식', food_type: '한식', distance_m: 120, estimated_walk_minutes: 3,
    matched_menus: [{ name: '김치찌개', price_krw: 9000 }, { name: '제육볶음', price_krw: 11000 }], business_hours: '매일 11:00~21:00',
    checks: [{ criterion: '예산', result: 'pass', value: '1만 2천원 이하 메뉴 2개', basis: '메뉴정보', hard: true }],
    score: 90, score_reasons: ['거리 감점'], unverified: [],
    cafes: [{ name: '카페1', source: 'kakao_local_category_CE7', source_id: 'k1', road_address: '서울 강남구 테헤란로 1', address: null,
              latitude: 37.4984, longitude: 127.0280, distance_m: 45, distance_basis: '카카오 제공 직선거리',
              estimated_walk_minutes: 1, place_url: 'http://place.map.kakao.com/1', phone: null }],
    cafe_notice: null,
    ...over,
  }
}

export function makeResult(over: Partial<ChatResponse> = {}): ChatResponse {
  return {
    session_id: 's1', run_id: 'r1', intent: 'recommend', intent_reason: '', decided_by: 'rule', message: '추천 결과예요',
    message_by: 'template', conditions: { base: { meal_period: '점심', meal_time: '12:00:00', cafe_time: null, visit_date: null } },
    clarify: false,
    weather: { forecast_datetime: '2026-11-19T12:00:00+09:00', temperature_c: 12, precipitation_probability: 20, precipitation_type: '없음', sky: '맑음' },
    weather_policy: ['일반 날씨 → 취향·예산·거리 중심'],
    recommendations: [makeRec(), makeRec({ name: '라멘가게', source_id: '6', latitude: 37.4991, longitude: 127.0287,
      matched_menus: [{ name: '돈코츠라멘', price_krw: 12000 }],
      cafes: [{ ...makeRec().cafes[0]!, name: '카페2', source_id: 'k2', latitude: 37.4993, longitude: 127.0290, distance_m: 60 }] })],
    excluded: [{ name: '스시', source: 's', source_id: '2', reason: '예산 조건 불충족' }], criteria: ['예산: 1만 2천원'],
    evidence: [], replans: [], stop_reason: null, suggestions: [], notices: [], disclaimer: null,
    saved_plan: null, plan_conflicts: [], events: [], elapsed_ms: 10,
    ...over,
  }
}

export function mockChat(result: () => unknown) {
  const fn = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url === '/api/health') {
      return { ok: true, status: 200, json: async () => ({ status: 'ok', api_keys: {}, llm: { available: true, provider: 'gms' }, tools: [], max_replans: 3 }) } as Response
    }
    return new Response(`event: result\ndata: ${JSON.stringify(result())}\n\n`, { status: 200 })
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

export function makeRouter() {
  return createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: ChatView }, { path: '/plans', component: PlansView }, { path: '/plans/:id', component: PlansView }] })
}
