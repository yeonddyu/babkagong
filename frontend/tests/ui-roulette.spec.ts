// UI 개선 5 — 메뉴 룰렛
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import MenuRoulette from '../src/components/MenuRoulette.vue'
import { makeRec, makeResult } from './helpers'

afterEach(() => vi.useRealTimers())

describe('메뉴 룰렛', () => {
  it('추천 코스의 가격 확인 메뉴만 후보로 쓰고 결과에 출처 코스를 붙인다', async () => {
    const recs = makeResult().recommendations // 김치찌개 9,000 · 제육볶음 11,000 (1번) / 돈코츠라멘 12,000 (2번)
    const w = mount(MenuRoulette, { props: { recommendations: recs, spinMs: 0, random: () => 0.99 } })
    expect(w.text()).toContain('메뉴 3개 중에서')
    await w.find('button.spin').trigger('click')
    expect(w.find('.window').text()).toContain('돈코츠라멘')
    expect(w.find('.window').text()).toContain('12,000원')
    expect(w.find('.window').text()).toContain('2번 코스 · 라멘가게')
    await w.find('button.go').trigger('click')
    expect(w.emitted('select')?.[0]).toEqual([1])
  })

  it('가격이 없는 메뉴는 제외하고, 후보가 2개 미만이면 룰렛을 숨긴다', () => {
    const recs = [makeRec({ matched_menus: [{ name: '가격없음', price_krw: null }, { name: '김치찌개', price_krw: 9000 }] })]
    const w = mount(MenuRoulette, { props: { recommendations: recs, spinMs: 0 } })
    expect(w.find('.roulette').exists()).toBe(false)
  })

  it('애니메이션 중에는 여러 메뉴를 보여 주다가 정해진 결과에서 멈춘다', async () => {
    vi.useFakeTimers()
    const recs = makeResult().recommendations
    const w = mount(MenuRoulette, { props: { recommendations: recs, spinMs: 1000, random: () => 0 } })
    await w.find('button.spin').trigger('click')
    expect(w.find('button.spin').attributes('disabled')).toBeDefined()
    await vi.advanceTimersByTimeAsync(1500)
    expect(w.find('.window').classes()).toContain('done')
    expect(w.find('.window').text()).toContain('김치찌개')
  })
})
