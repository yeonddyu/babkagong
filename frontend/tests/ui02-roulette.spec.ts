// UI-02 원형 메뉴 룰렛
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import MenuRoulette from '../src/components/MenuRoulette.vue'
import ChatView from '../src/views/ChatView.vue'
import { courseState, resetCourse } from '../src/stores/course'
import { makeRec, makeResult, makeRouter, mockChat } from './helpers'

beforeEach(() => resetCourse())
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('원형 룰렛', () => {
  it('추천 코스의 실제 메뉴로 칸을 만들고, 결과 칸이 바늘 위치에 오도록 돈다', async () => {
    const recs = makeResult().recommendations // 김치찌개·제육볶음(1번) / 돈코츠라멘(2번)
    const w = mount(MenuRoulette, { props: { recommendations: recs, spinMs: 0, random: () => 0.5 } })
    const labels = w.findAll('.slice-label').map((t) => t.text())
    expect(labels).toEqual(['김치찌개', '돈코츠라멘', '제육볶음']) // 코스를 번갈아 올림
    await w.find('button.spin').trigger('click')
    // 3칸 중 index 1 → 360 - (120 + 60) = 180, 5바퀴 + 180
    expect(w.find('svg.wheel').attributes('style')).toContain('rotate(1980deg)')
    expect(w.find('.result .menu').text()).toBe('돈코츠라멘')
    expect(w.find('.result .price').text()).toContain('12,000원')
    expect(w.find('.result .where').text()).toBe('라멘가게')
    expect(w.find('.result .reason').text()).toContain('예산 충족')
  })

  it('애니메이션 동안 버튼을 막고, 끝나면 결과를 보여 준다 (다시 돌리기)', async () => {
    vi.useFakeTimers()
    const w = mount(MenuRoulette, { props: { recommendations: makeResult().recommendations, spinMs: 3000, random: () => 0 } })
    await w.find('button.spin').trigger('click')
    expect(w.find('button.spin').text()).toBe('돌아가는 중…')
    expect(w.find('.result').exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(3000)
    expect(w.find('.result .menu').text()).toBe('김치찌개')
    expect(w.find('button.spin').text()).toBe('다시 돌리기')
  })

  it('움직임 줄이기 설정이면 회전 애니메이션 없이 바로 결과를 보여 준다', async () => {
    vi.stubGlobal('matchMedia', (q: string) => ({ matches: q.includes('reduce'), media: q, addEventListener() {}, removeEventListener() {} }))
    const w = mount(MenuRoulette, { props: { recommendations: makeResult().recommendations, spinMs: 3000, random: () => 0 } })
    await w.find('button.spin').trigger('click')
    expect(w.find('.result .menu').text()).toBe('김치찌개')
    expect(w.find('svg.wheel').attributes('style')).toContain('transition-duration: 0ms')
  })

  it('10개를 넘는 메뉴는 코스별로 번갈아 10칸만 올리고 그 사실을 알린다', () => {
    const many = Array.from({ length: 8 }, (_, k) => ({ name: `메뉴${k}`, price_krw: 8000 + k }))
    const recs = [makeRec({ matched_menus: many }), makeRec({ name: 'B', source_id: 'b', matched_menus: many.map((m) => ({ ...m, name: `B${m.name}` })) })]
    const w = mount(MenuRoulette, { props: { recommendations: recs, spinMs: 0 } })
    expect(w.findAll('.slice-label')).toHaveLength(10)
    expect(w.text()).toContain('메뉴 16개 중 10개를 올렸어요')
  })

  it('메뉴가 부족하면 추천 식당 뽑기로 바꾼다 (메뉴·가격을 만들지 않음)', async () => {
    const recs = ['쌀국수집', '백반집'].map((n, i) => makeRec({ name: n, source_id: `r${i}`, matched_menus: [], sample_menus: [] }))
    const w = mount(MenuRoulette, { props: { recommendations: recs, spinMs: 0, random: () => 0.9 } })
    expect(w.find('h3').text()).toBe('오늘 뭐 먹지? 식당 뽑기')
    await w.find('button.spin').trigger('click')
    expect(w.find('.result .menu').text()).toBe('백반집')
    expect(w.find('.result .price').exists()).toBe(false)
    expect(w.find('.result .actions button').text()).toBe('이 식당 코스 보기')
  })
})

describe('룰렛 결과를 추천 코스로 연결', () => {
  it("'이 메뉴로 식당 찾기'를 누르면 그 코스가 선택되고 지도에서 식당 정보가 열린다", async () => {
    mockChat(() => makeResult())
    const w = mount(ChatView, { global: { plugins: [makeRouter()] } })
    await w.find('form.composer input').setValue('강남역 1만 2천원 이하 점심')
    await w.find('form.composer').trigger('submit')
    await flushPromises()
    vi.spyOn(Math, 'random').mockReturnValue(0.5) // 기본 random 은 Math.random
    vi.useFakeTimers()
    const roulette = w.findComponent(MenuRoulette)
    await roulette.find('button.spin').trigger('click')
    await vi.advanceTimersByTimeAsync(3200)
    await roulette.find('.result .actions button').trigger('click')
    expect(courseState.selected).toBe(1)
    expect(courseState.focus).toEqual({ kind: 'meal', course: 1, cafe: 0 })
    expect(w.findAll('.rec-wrap')[1]!.classes()).toContain('on')
    expect(w.find('.place-card h4').text()).toBe('라멘가게')
  })
})
