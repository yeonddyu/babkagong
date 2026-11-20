// F3018 화면 - 컴포넌트 테스트 (fetch 를 가짜로 대체. 실제 백엔드 연동은 브라우저에서 별도 확인)
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import RecommendationCard from '../src/components/RecommendationCard.vue'
import PlansView from '../src/views/PlansView.vue'
import ChatView from '../src/views/ChatView.vue'
import type { Plan, Recommendation } from '../src/types'

const rec: Recommendation = {
  name: '김치찌개집', source: 'seoul_tourism_redtable', source_id: '1', address: '서울 강남구 테스트로 1', area: '강남역',
  latitude: 37.4981, longitude: 127.0277,
  category: '한식', food_type: '한식', distance_m: 120, estimated_walk_minutes: 3,
  matched_menus: [{ name: '김치찌개', price_krw: 9000 }], business_hours: null,
  checks: [{ criterion: '예산', result: 'pass', value: '1만원 이하 메뉴 1개', basis: '메뉴정보', hard: true },
           { criterion: '영업시간', result: 'unknown', value: '영업시간 미확인', basis: '', hard: false }],
  score: 90, score_reasons: ['거리 감점'], unverified: ['영업시간 미확인 — 12:00 영업 여부를 방문 전 확인 필요'],
  cafes: [{ name: '카페1', source: 'gangnam_rest_food_license', source_id: 'x', road_address: null, address: '역삼동',
            latitude: 37.4983, longitude: 127.0279, distance_m: 50,
            distance_basis: '직선', estimated_walk_minutes: 1, place_url: null, phone: null }],
  cafe_notice: null,
}

const plan = (id: number, title: string, start = '12:00:00', end = '15:00:00'): Plan => ({
  id, title, plan_date: '2026-11-20', start_time: start, end_time: end, area: '강남역', restaurant_name: '식당',
  restaurant_source: null, restaurant_source_id: null, restaurant_address: null, cafe_name: null, cafe_source: null,
  cafe_source_id: null, cafe_address: null, cafe_url: null, memo: null, session_id: null,
  created_at: '2026-11-19T10:00:00+09:00', updated_at: '2026-11-19T10:00:00+09:00',
})

function mockFetch(handler: (url: string, init?: RequestInit) => unknown) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const body = handler(url, init)
    return { ok: true, status: 200, json: async () => body } as Response
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

// /api/chat/stream 은 SSE 본문, /api/health 는 JSON 으로 응답하는 가짜 fetch
function mockChat(result: () => unknown, progress: unknown[] = []) {
  const fn = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url === '/api/health') {
      return { ok: true, status: 200, json: async () => ({ status: 'ok', api_keys: {}, llm: { available: true }, tools: [], max_replans: 3 }) } as Response
    }
    const sse = progress.map((p) => `event: progress\ndata: ${JSON.stringify(p)}\n\n`).join('') +
      `event: result\ndata: ${JSON.stringify(result())}\n\n`
    return new Response(sse, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

function makeRouter() {
  return createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: ChatView }, { path: '/plans', component: PlansView }, { path: '/plans/:id', component: PlansView }] })
}

afterEach(() => vi.unstubAllGlobals())

describe('RecommendationCard', () => {
  it('확인된 값과 미확인 값을 구분해 표시하고 없는 값을 만들지 않는다', () => {
    const w = mount(RecommendationCard, { props: { rec, index: 0 } })
    const text = w.text()
    expect(text).toContain('김치찌개 9,000원')
    expect(text).toContain('영업시간 미확인')
    expect(text).toContain('예산 충족')
    expect(text).toContain('영업시간 미확인')
    expect(text).toContain('도보 약 3분(추정)')
    expect(text).toContain('콘센트·와이파이')
    expect(w.find('.cafes a').exists()).toBe(false) // 링크 없는 보조 출처 카페는 링크를 만들지 않음
  })

  it('저장 버튼이 이벤트를 보낸다', async () => {
    const w = mount(RecommendationCard, { props: { rec, index: 2 } })
    await w.find('button.save').trigger('click')
    expect(w.emitted('save')?.[0]).toEqual([2])
  })
})

describe('ChatView', () => {
  it('선택한 지역과 메시지로 대화 API 를 호출하고 추천을 표시한다', async () => {
    const fetch = mockChat(() => ({
      session_id: 's1', run_id: 'r1', intent: 'recommend', intent_reason: '', decided_by: 'rule', message: '추천 결과예요',
      message_by: 'template', conditions: {}, clarify: false, weather: null, weather_policy: [], recommendations: [rec],
      excluded: [{ name: '스시', source: 's', source_id: '2', reason: '예산 조건 불충족' }], criteria: ['예산: 1만원'],
      evidence: [], replans: [], stop_reason: null, suggestions: [], notices: ['날씨 조회: API 키가 설정되지 않아 확인하지 못했습니다'],
      disclaimer: null, saved_plan: null, plan_conflicts: [], events: [], elapsed_ms: 10,
    }))
    const router = makeRouter()
    const w = mount(ChatView, { global: { plugins: [router] } })
    await flushPromises()
    await w.findAll('.area-btn').find((b) => b.text() === '역삼')!.trigger('click')
    await w.find('form.composer input').setValue('점심 추천')
    await w.find('form.composer').trigger('submit')
    await flushPromises()
    const [url, init] = fetch.mock.calls.find(([u]) => u !== '/api/health' && u !== '/api/stations')!
    expect(url).toBe('/api/chat/stream')
    expect(JSON.parse(init!.body as string)).toEqual({ message: '점심 추천', session_id: null, area: '역삼역' })
    expect(w.text()).toContain('추천 결과예요')
    expect(w.text()).toContain('김치찌개집')
    expect(w.text()).toContain('API 키가 설정되지 않아')
    expect(w.text()).toContain('예산 조건 불충족')
  })
})

describe('PlansView', () => {
  it('목록·상세를 불러오고 수정 결과(충돌 안내)를 목록에 반영한다', async () => {
    let plans = [plan(1, '점심 A'), plan(2, '점심 B', '16:00:00', '17:00:00')]
    const fetch = mockFetch((_url, init) => {
      if (init?.method === 'PUT') {
        plans = [plans[0]!, { ...plans[1]!, title: '수정됨', start_time: '13:00:00' }]
        return { plan: plans[1], conflicts: [{ id: 1, title: '점심 A', plan_date: '2026-11-20', start_time: '12:00:00', end_time: '15:00:00' }] }
      }
      return { plans }
    })
    const router = makeRouter()
    router.push('/plans/2')
    await router.isReady()
    const w = mount(PlansView, { global: { plugins: [router] } })
    await flushPromises()
    expect(w.findAll('.list li')).toHaveLength(2)
    expect(w.find('.detail h2').text()).toBe('점심 B')
    await w.find('.actions .btn.primary').trigger('click')
    await w.find('.edit input').setValue('수정됨')
    await w.find('form.edit').trigger('submit')
    await flushPromises()
    expect(fetch.mock.calls.some(([u, i]) => u === '/api/plans/2' && i?.method === 'PUT')).toBe(true)
    expect(w.text()).toContain('겹치는 계획')
    expect(w.findAll('.list li')[1]!.text()).toContain('수정됨')
  })

  it('삭제하면 목록에서 사라진다', async () => {
    let plans = [plan(1, '지울 계획')]
    mockFetch((_u, init) => {
      if (init?.method === 'DELETE') { plans = []; return { deleted: true } }
      return { plans }
    })
    vi.stubGlobal('confirm', () => true)
    const router = makeRouter()
    router.push('/plans/1')
    await router.isReady()
    const w = mount(PlansView, { global: { plugins: [router] } })
    await flushPromises()
    await w.find('.btn.danger').trigger('click')
    await flushPromises()
    expect(w.findAll('.list li')).toHaveLength(0)
    expect(w.text()).toContain('삭제했어요')
  })
})
