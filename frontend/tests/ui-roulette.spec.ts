// UI 개선 5 — 메뉴 룰렛 (UI-02 원형 룰렛으로 바뀐 뒤에도 유지해야 하는 후보 규칙)
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MenuRoulette from '../src/components/MenuRoulette.vue'
import { makeRec, makeResult } from './helpers'

describe('메뉴 룰렛 후보 규칙', () => {
  it('추천 코스의 가격 확인 메뉴만 후보로 쓰고 결과에 출처 코스를 붙인다', async () => {
    const recs = makeResult().recommendations // 김치찌개 9,000 · 제육볶음 11,000 (1번) / 돈코츠라멘 12,000 (2번)
    const w = mount(MenuRoulette, { props: { recommendations: recs, spinMs: 0, random: () => 0.99 } })
    expect(w.text()).toContain('메뉴 3개 중에서')
    await w.find('button.spin').trigger('click')
    expect(w.find('.result .menu').text()).toBe('제육볶음')
    expect(w.find('.result').text()).toContain('1번 코스')
    expect(w.find('.result .where').text()).toBe('김치찌개집')
    await w.find('.result .actions button').trigger('click')
    expect(w.emitted('select')?.[0]).toEqual([0])
  })

  it('가격이 없는 메뉴는 제외하고, 식당도 1곳뿐이면 돌릴 수 없는 이유를 안내한다', () => {
    const recs = [makeRec({ matched_menus: [{ name: '가격없음', price_krw: null }, { name: '김치찌개', price_krw: 9000 }] })]
    const w = mount(MenuRoulette, { props: { recommendations: recs, spinMs: 0 } })
    expect(w.find('.roulette').classes()).toContain('mode-none')
    expect(w.text()).toContain('룰렛을 돌릴 수 없어요')
    expect(w.find('button.spin').exists()).toBe(false)
  })

  it('예산 조건이 없으면 대표 메뉴(sample_menus)로 메뉴 룰렛을 돌린다', async () => {
    const recs = [makeRec({ matched_menus: [], sample_menus: [{ name: '쌀국수', price_krw: 9500 }] }),
                  makeRec({ name: '분식집', source_id: '9', matched_menus: [], sample_menus: [{ name: '떡볶이', price_krw: 4500 }] })]
    const w = mount(MenuRoulette, { props: { recommendations: recs, spinMs: 0, random: () => 0.9 } })
    expect(w.find('h3').text()).toBe('오늘 뭐 먹지?')
    await w.find('button.spin').trigger('click')
    expect(w.find('.result .menu').text()).toBe('떡볶이')
    expect(w.find('.result .price').text()).toContain('4,500원')
  })

  it('확인된 메뉴가 부족하면 추천 식당 뽑기로 바꾸고 메뉴를 지어내지 않는다', async () => {
    const recs = ['쌀국수집', '백반집', '분식집'].map((n, i) =>
      makeRec({ name: n, source_id: `r${i}`, matched_menus: [], sample_menus: [] }))
    const w = mount(MenuRoulette, { props: { recommendations: recs, spinMs: 0, random: () => 0.5 } })
    expect(w.text()).toContain('추천된 식당 3곳 중에서')
    await w.find('button.spin').trigger('click')
    expect(w.find('.result .menu').text()).toBe('백반집')
    expect(w.find('.result .price').exists()).toBe(false)
    await w.find('.result .actions button').trigger('click')
    expect(w.emitted('select')?.[0]).toEqual([1])
  })

  it('지도에서 위치 확인 버튼은 locate 로 코스를 알린다', async () => {
    const w = mount(MenuRoulette, { props: { recommendations: makeResult().recommendations, spinMs: 0, random: () => 0.5 } })
    await w.find('button.spin').trigger('click')
    await w.findAll('.result .actions button')[1]!.trigger('click')
    expect(w.emitted('locate')?.[0]).toEqual([1])
  })
})
