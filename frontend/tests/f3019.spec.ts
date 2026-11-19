// F3019 실행 과정 및 상태 표시 - 컴포넌트 테스트
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import RunTimeline from '../src/components/RunTimeline.vue'
import StatusBanner from '../src/components/StatusBanner.vue'
import type { RunEvent } from '../src/types'

let seq = 0
const ev = (type: string, stage: string | null, payload: Record<string, unknown> = {}): RunEvent =>
  ({ session_id: 's', run_id: 'r', seq: ++seq, type, stage, payload, timestamp: '2026-11-19T12:00:00+09:00' })

const events = (): RunEvent[] => {
  seq = 0
  return [
    ev('run_start', null),
    ev('stage_start', 'analyze'),
    ev('llm_decision', 'analyze', { decision: 'intent=recommend', reason: '추천 요청', decided_by: 'rule' }),
    ev('stage_start', 'plan'),
    ev('plan_created', 'plan', { mode: 'tools', reason: '', steps: [{ tool: 'get_weather_context' }, { tool: 'search_restaurant_candidates' }] }),
    ev('stage_start', 'execute'),
    ev('tool_call', 'execute', { tool: 'get_weather_context', args: {} }),
    ev('tool_result', 'execute', { tool: 'get_weather_context', ok: false, error_code: 'MISSING_API_KEY', error_message: 'KMA_API_KEY secret-detail', duration_ms: 3 }),
    ev('tool_call', 'execute', { tool: 'search_restaurant_candidates', args: {} }),
    ev('tool_result', 'execute', { tool: 'search_restaurant_candidates', ok: true, summary: '후보 30곳', duration_ms: 120 }),
    ev('stage_start', 'judge'),
    ev('stage_end', 'judge', { satisfied: 0, excluded: 6, next: 'replan' }),
    ev('stage_start', 'replan'),
    ev('replan', 'replan', { count: 1, limit: 3, reason: '충족 후보 0건', strategy: 'next_batch', detail: '다음 후보 조회' }),
    ev('tool_reuse', 'execute', { tool: 'search_restaurant_candidates', args: {} }),
    ev('run_end', null),
  ]
}

afterEach(() => vi.unstubAllGlobals())

describe('RunTimeline', () => {
  it('단계·Tool 호출을 실행 순서대로, 재계획 지점과 실패를 구분해 표시한다', () => {
    const w = mount(RunTimeline, { props: { events: events(), elapsedMs: 2500 } })
    const items = w.findAll('li').map((li) => li.text())
    expect(items[0]).toContain('요청 분석')
    const tools = w.findAll('li.tool').map((li) => li.text())
    expect(tools[0]).toContain('날씨 조회')
    expect(tools[1]).toContain('음식점 후보 조회')
    expect(items.findIndex((t) => t.includes('재계획'))).toBeGreaterThan(items.findIndex((t) => t.includes('조건 충족 0곳')))
    expect(w.find('li.replan').text()).toContain('재계획 1/3회')
    expect(w.find('li.bad').text()).toContain('API 키 누락')
    expect(w.text()).not.toContain('secret-detail') // 오류 상세 미노출
    expect(w.text()).toContain('이전 결과 재사용')
    expect(w.text()).toContain('Tool 2회 · 재계획 1회 · 실패 1건 · 2.5초')
  })

  it('처리 중에는 현재 단계를 보여 준다', () => {
    const live = events().slice(0, 7)
    const w = mount(RunTimeline, { props: { events: live, live: true } })
    expect(w.find('.spinner').exists()).toBe(true)
    expect(w.text()).toContain('처리 중 — 날씨 조회 호출 중')
  })
})

describe('StatusBanner', () => {
  it('키가 없는 기능만 이름으로 안내하고 키 값은 표시하지 않는다', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => ({
      status: 'ok', api_keys: { REDTABLE_API_KEY: true, KAKAO_REST_API_KEY: false, OPENAI_API_KEY: false },
      llm: { available: false, provider: 'gms' }, tools: [], max_replans: 3 }) })))
    const w = mount(StatusBanner)
    await flushPromises()
    expect(w.text()).toContain('카카오 로컬(카페 검색)')
    expect(w.text()).not.toContain('서울관광재단')
    expect(w.text()).not.toContain('OpenAI')
    expect(w.text()).toContain('AI 모델(GMS)')
    expect(w.text()).toContain('규칙 기반')
  })

  it('GMS 로 LLM 을 쓸 수 있으면 OPENAI_API_KEY 가 없어도 경고하지 않는다', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => ({
      status: 'ok', api_keys: { REDTABLE_API_KEY: true, KAKAO_REST_API_KEY: true, KMA_API_KEY: true, SEOUL_OPENAPI_KEY: true,
                                OPENAI_API_KEY: false, GMS_API_KEY: true },
      llm: { available: true, provider: 'gms' }, tools: [], max_replans: 3 }) })))
    const w = mount(StatusBanner)
    await flushPromises()
    expect(w.find('.notice').exists()).toBe(false)
  })

  it('서버 연결 실패를 안내한다', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('fail') }))
    const w = mount(StatusBanner)
    await flushPromises()
    expect(w.text()).toContain('서버에 연결할 수 없어요')
  })
})
