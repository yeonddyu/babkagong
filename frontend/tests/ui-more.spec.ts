// 추천 5곳 + '다른 곳 더 보기'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ChatView from '../src/views/ChatView.vue'
import { makeRec, makeResult, makeRouter, mockChat } from './helpers'

afterEach(() => vi.unstubAllGlobals())

const five = (prefix: string) => Array.from({ length: 5 }, (_, i) =>
  makeRec({ name: `${prefix}${i + 1}`, source_id: `${prefix}${i}`, latitude: 37.498 + i * 0.0002 }))

describe('다른 곳 더 보기', () => {
  it('버튼을 누르면 같은 세션으로 더 보기 요청을 보내고 새 코스 5곳으로 바꾼다', async () => {
    let call = 0
    const fetch = mockChat(() => (++call === 1
      ? makeResult({ recommendations: five('첫') })
      : makeResult({ recommendations: five('새'), more: true })))
    const w = mount(ChatView, { global: { plugins: [makeRouter()] } })
    await w.find('input').setValue('강남역 점심')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.find('aside.side').findAll('article.rec')).toHaveLength(5)
    expect(w.find('.more-note').exists()).toBe(false)

    await w.find('button.more-btn').trigger('click')
    await flushPromises()
    const bodies = fetch.mock.calls.filter(([u]) => u === '/api/chat/stream').map(([, i]) => JSON.parse(i!.body as string))
    expect(bodies[1]).toEqual({ message: '다른 곳 더 보여줘', session_id: 's1', area: '강남역' })
    const names = w.find('aside.side').findAll('article.rec h3').map((h) => h.text())
    expect(names).toEqual(['새1', '새2', '새3', '새4', '새5'])
    expect(w.find('.more-note').text()).toContain('앞서 보여 드린 곳은 빼고')
    expect(w.findAll('section.chat .course-chips')).toHaveLength(2) // 이전 답변의 칩은 남되 비활성
    expect(w.findAll('section.chat .course-chips')[0]!.find('button').attributes('disabled')).toBeDefined()
  })

  it('추천이 없으면 더 보기 버튼을 보여 주지 않는다', async () => {
    mockChat(() => makeResult({ recommendations: [], stop_reason: '재계획 상한(3회)에 도달', suggestions: ['예산 올리기'] }))
    const w = mount(ChatView, { global: { plugins: [makeRouter()] } })
    await w.find('input').setValue('강남역 1천원 점심')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.find('button.more-btn').exists()).toBe(false)
    expect(w.text()).toContain('조건에 맞는 코스를 찾지 못했어요')
  })
})
