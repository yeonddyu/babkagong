// UI 개선 1 — 2단 레이아웃·모바일 탭
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ChatView from '../src/views/ChatView.vue'
import { makeResult, makeRouter, mockChat } from './helpers'

afterEach(() => vi.unstubAllGlobals())

async function ask() {
  mockChat(() => makeResult())
  const w = mount(ChatView, { global: { plugins: [makeRouter()] } })
  await w.find('input').setValue('강남역 점심')
  await w.find('form').trigger('submit')
  await flushPromises()
  return w
}

describe('2단 레이아웃', () => {
  it('대화 영역과 코스 영역이 나뉘고 추천 카드는 코스 영역에만 한 번 나온다', async () => {
    const w = await ask()
    expect(w.find('section.chat').exists()).toBe(true)
    expect(w.find('aside.side').findAll('article.rec')).toHaveLength(2)
    expect(w.find('section.chat').findAll('article.rec')).toHaveLength(0)
    expect(w.find('section.chat').findAll('.chip').map((c) => c.text())).toEqual(['1. 김치찌개집', '2. 라멘가게'])
  })

  it('대화의 코스 칩을 누르면 해당 코스가 선택되고 모바일에서는 코스 탭으로 넘어간다', async () => {
    const w = await ask()
    expect(w.find('.workspace').attributes('data-tab')).toBe('chat')
    await w.findAll('.chip')[1]!.trigger('click')
    expect(w.find('.workspace').attributes('data-tab')).toBe('course')
    expect(w.findAll('.rec-wrap')[1]!.classes()).toContain('on')
    await w.findAll('.mobile-tabs button')[0]!.trigger('click')
    expect(w.find('.workspace').attributes('data-tab')).toBe('chat')
  })

  it('추천 전에는 코스 영역이 다음 행동을 안내한다', () => {
    mockChat(() => makeResult())
    const w = mount(ChatView, { global: { plugins: [makeRouter()] } })
    expect(w.find('aside.side').text()).toContain('아직 고른 코스가 없어요')
  })
})

describe('응답 문장 표시', () => {
  it('굵게 표기만 강조하고 HTML 은 실행하지 않는다', async () => {
    const { formatMessage } = await import('../src/utils/format')
    expect(formatMessage('**명가** <script>x</script>')).toBe('<strong>명가</strong> &lt;script&gt;x&lt;/script&gt;')
  })
})
