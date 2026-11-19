// UI 개선 3 — 시각적 추천 카드
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import RecommendationCard from '../src/components/RecommendationCard.vue'
import { makeRec } from './helpers'

describe('추천 카드', () => {
  it('대표 카페만 펼쳐 보이고 나머지 카페와 판단 근거는 접어 둔다', () => {
    const base = makeRec()
    const rec = makeRec({ cafes: [base.cafes[0]!, { ...base.cafes[0]!, name: '카페B', source_id: 'b' }, { ...base.cafes[0]!, name: '카페C', source_id: 'c' }] })
    const w = mount(RecommendationCard, { props: { rec, index: 0 } })
    expect(w.find('.main-cafe').text()).toContain('카페1')
    expect(w.find('.main-cafe a').attributes('href')).toBe('http://place.map.kakao.com/1')
    expect(w.find('details.more summary').text()).toBe('근처 카페 2곳 더 보기')
    expect(w.find('details.more').attributes('open')).toBeUndefined()
    expect(w.find('details.basis').text()).toContain('1만 2천원 이하 메뉴 2개') // 근거 값은 그대로 보존
    expect(w.findAll('.menu').map((m) => m.text())).toEqual(['김치찌개 9,000원', '제육볶음 11,000원'])
  })

  it('영업시간이 없으면 미확인으로 구분해 표시한다', () => {
    const w = mount(RecommendationCard, { props: { rec: makeRec({ business_hours: null }), index: 0 } })
    const fact = w.findAll('.fact').find((f) => f.text() === '영업시간 미확인')
    expect(fact?.classes()).toContain('unknown')
  })

  it('저장 버튼은 카드 선택 클릭과 분리된다', async () => {
    const w = mount(RecommendationCard, { props: { rec: makeRec(), index: 1 }, attachTo: document.body })
    let parentClicks = 0
    w.element.parentElement!.addEventListener('click', () => parentClicks++)
    await w.find('button.save').trigger('click')
    expect(w.emitted('save')?.[0]).toEqual([1])
    expect(parentClicks).toBe(0)
    w.unmount()
  })
})
