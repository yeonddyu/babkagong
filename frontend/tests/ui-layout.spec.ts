// UI-04 레이아웃: 왼쪽(마스코트·대화·룰렛·카드) / 오른쪽(지도), 모바일 대화·지도 탭, 짧은 대화 요약
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ChatView from '../src/views/ChatView.vue'
import { courseState, resetCourse } from '../src/stores/course'
import { makeResult, makeRouter, mockChat } from './helpers'

beforeEach(() => resetCourse())
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

async function ask(over = {}) {
  mockChat(() => makeResult(over))
  const w = mount(ChatView, { global: { plugins: [makeRouter()] }, attachTo: document.body })
  await w.find('form.composer input').setValue('강남역 점심')
  await w.find('form.composer').trigger('submit')
  await flushPromises()
  return w
}

describe('2단 레이아웃 (왼쪽 45 : 오른쪽 55)', () => {
  it('왼쪽은 마스코트 → 지역 → 대화 → 룰렛 → 추천 카드 순서, 오른쪽은 지도만', async () => {
    const w = await ask()
    const left = w.find('.left')
    const order = ['.mascot', '.toolbar', 'section.chat', '.roulette', '.course-timeline', '.recs']
      .map((sel) => Array.from(left.element.querySelectorAll('*')).indexOf(left.element.querySelector(sel)!))
    expect(order.every((v) => v >= 0)).toBe(true)
    expect([...order].sort((a, b) => a - b)).toEqual(order)
    expect(left.findAll('article.rec')).toHaveLength(2) // 카드는 한 번만
    expect(w.find('aside.mapside .map-card').exists()).toBe(true)
    expect(w.find('aside.mapside').findAll('article.rec')).toHaveLength(0)
    expect(w.find('section.chat').findAll('.chip').map((c) => c.text())).toEqual(['1. 김치찌개집', '2. 라멘가게'])
    w.unmount()
  })

  it('추천 전에는 지도 자리에서 다음 행동을 안내한다', () => {
    mockChat(() => makeResult())
    const w = mount(ChatView, { global: { plugins: [makeRouter()] } })
    expect(w.find('aside.mapside').text()).toContain('아직 고른 코스가 없어요')
    expect(w.find('.course-panel').exists()).toBe(false)
  })
})

describe('대화창은 짧게, 자세한 내용은 카드·지도에', () => {
  it('요약이 있으면 요약만 보이고 전체 답변은 펼쳐서 본다', async () => {
    const w = await ask({ summary: '조건에 맞는 코스 2개를 찾았어요. 1순위는 **김치찌개집**.', message: '긴 전체 답변\n1. 김치찌개집 ...' })
    const bot = w.find('.bubble.bot')
    expect(bot.find('.msg.summary').html()).toContain('<strong>김치찌개집</strong>')
    expect(bot.find('details.full summary').text()).toBe('전체 답변 보기')
    expect(bot.find('details.full').attributes('open')).toBeUndefined()
    expect(bot.find('details.full .msg').text()).toContain('긴 전체 답변')
    w.unmount()
  })

  it('요약이 없으면(결과 없음 등) 전체 메시지를 그대로 보여 준다', async () => {
    const w = await ask({ summary: null, message: '조건을 모두 만족하는 식당을 찾지 못했어요.', recommendations: [] })
    expect(w.find('.bubble.bot details.full').exists()).toBe(false)
    expect(w.find('.bubble.bot .msg').text()).toBe('조건을 모두 만족하는 식당을 찾지 못했어요.')
    w.unmount()
  })
})

describe('코스 선택과 화면 이동', () => {
  it('대화의 코스 칩을 누르면 그 코스가 선택되고 해당 카드로 스크롤한다', async () => {
    const scrolled: string[] = []
    Element.prototype.scrollIntoView = function () { scrolled.push((this as Element).id) }
    const w = await ask()
    await w.findAll('.chip')[1]!.trigger('click')
    await flushPromises()
    expect(courseState.selected).toBe(1)
    expect(w.findAll('.rec-wrap')[1]!.classes()).toContain('on')
    expect(scrolled).toContain('course-1')
    expect(w.find('.workspace').attributes('data-tab')).toBe('chat')
    w.unmount()
  })

  it('모바일에서 카드의 지도 보기를 누르면 지도 탭으로 바뀌고, 탭으로 대화에 돌아온다', async () => {
    vi.stubGlobal('matchMedia', (q: string) => ({ matches: q.includes('max-width'), media: q, addEventListener() {}, removeEventListener() {} }))
    window.scrollTo = vi.fn() as any
    const w = await ask()
    expect(w.find('.workspace').attributes('data-tab')).toBe('chat')
    await w.findAll('article.rec')[1]!.find('button.map-btn').trigger('click')
    await flushPromises()
    expect(w.find('.workspace').attributes('data-tab')).toBe('map')
    expect(w.find('.place-card h4').text()).toBe('라멘가게')
    await w.findAll('.mobile-tabs button')[0]!.trigger('click')
    expect(w.find('.workspace').attributes('data-tab')).toBe('chat')
    w.unmount()
  })
})

describe('응답 문장 표시', () => {
  it('굵게 표기만 강조하고 HTML 은 실행하지 않는다', async () => {
    const { formatMessage } = await import('../src/utils/format')
    expect(formatMessage('**명가** <script>x</script>')).toBe('<strong>명가</strong> &lt;script&gt;x&lt;/script&gt;')
  })
})

describe('역 선택 (역삼역 주변 6곳)', () => {
  it('서비스 역 6곳을 버튼으로 보여 주고, 고른 역으로 요청한다', async () => {
    const fetch = mockChat(() => makeResult())
    const w = mount(ChatView, { global: { plugins: [makeRouter()] } })
    await flushPromises()
    expect(w.findAll('.area-btn').map((b) => b.text())).toEqual(['역삼', '강남', '언주', '신논현', '선릉', '선정릉'])
    await w.findAll('.area-btn')[4]!.trigger('click')
    expect(w.find('.area-btn.on').text()).toBe('선릉')
    expect(w.find('.area-hint').text()).toBe('역 이름 없이 보내면 선릉역 주변에서 찾아요')
    await w.find('form.composer input').setValue('점심 먹고 카공')
    await w.find('form.composer').trigger('submit')
    await flushPromises()
    const body = JSON.parse(fetch.mock.calls.find(([u]) => u === '/api/chat/stream')![1]!.body as string)
    expect(body.area).toBe('선릉역')
  })
})

describe('예시 질문', () => {
  it('고른 역에 맞춰 예시 질문이 바뀌고, 누르면 그 문장을 보낸다', async () => {
    const fetch = mockChat(() => makeResult())
    const w = mount(ChatView, { global: { plugins: [makeRouter()] } })
    await flushPromises()
    expect(w.findAll('.example')[0]!.text()).toBe('강남역에서 점심 먹고 카공할 건데 추천해줘')
    await w.findAll('.area-btn').find((b) => b.text() === '선정릉')!.trigger('click')
    const texts = w.findAll('.example').map((b) => b.text())
    expect(texts).toHaveLength(4)
    expect(texts.every((t) => t.includes('선정릉역'))).toBe(true)
    await w.findAll('.example')[3]!.trigger('click')
    await flushPromises()
    const body = JSON.parse(fetch.mock.calls.find(([u]) => u === '/api/chat/stream')![1]!.body as string)
    expect(body).toMatchObject({ message: '선정릉역 도보 5분 이내에서 저녁 먹고 카공', area: '선정릉역' })
  })
})

describe('키보드 조작 (Codex 2차 검증 결함 7)', () => {
  it('모바일 탭은 방향키·Home·End 로 포커스와 탭이 함께 이동한다', async () => {
    mockChat(() => makeResult())
    const w = mount(ChatView, { global: { plugins: [makeRouter()] }, attachTo: document.body })
    const tabs = w.findAll('[role="tab"]')
    expect(tabs.map((t) => t.attributes('tabindex'))).toEqual(['0', '-1'])
    expect(tabs[0]!.attributes('aria-controls')).toBe('panel-chat')
    await tabs[0]!.trigger('keydown', { key: 'ArrowRight' })
    await flushPromises()
    expect(w.find('.workspace').attributes('data-tab')).toBe('map')
    expect(document.activeElement?.id).toBe('tab-map')
    expect(w.findAll('[role="tab"]').map((t) => t.attributes('tabindex'))).toEqual(['-1', '0'])
    await w.find('#tab-map').trigger('keydown', { key: 'ArrowLeft' })
    await flushPromises()
    expect(w.find('.workspace').attributes('data-tab')).toBe('chat')
    expect(document.activeElement?.id).toBe('tab-chat')
    await w.find('#tab-chat').trigger('keydown', { key: 'End' })
    expect(w.find('.workspace').attributes('data-tab')).toBe('map')
    w.unmount()
  })
})
