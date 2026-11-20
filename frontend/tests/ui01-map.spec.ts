// UI-01 인터랙티브 지도: 정보 카드, 카페 바꾸기, 카드·지도 상태 연동, 지도 실패 시 장소 목록, 저장 코스 지도
/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import MapPanel from '../src/components/MapPanel.vue'
import ChatView from '../src/views/ChatView.vue'
import PlansView from '../src/views/PlansView.vue'
import { courseState, resetCourse } from '../src/stores/course'
import { makeRec, makeResult, makeRouter, mockChat } from './helpers'

const threeCafes = () => {
  const base = makeRec().cafes[0]!
  return [base, { ...base, name: '카페B', source_id: 'b', latitude: 37.4990, longitude: 127.0290, distance_m: 150, place_url: null },
          { ...base, name: '카페C', source_id: 'c', latitude: 37.4970, longitude: 127.0260, distance_m: 210 }]
}

beforeEach(() => resetCourse())
afterEach(() => { vi.unstubAllGlobals(); delete (window as any).kakao })

describe('지도 정보 카드', () => {
  it('식당 핀을 누르면 메뉴·영업·추천 이유를, 없는 값은 확인 필요로 보여 준다', async () => {
    const recs = [makeRec({ business_hours: null })]
    const w = mount(MapPanel, { props: { recommendations: recs, selected: 0 } })
    await flushPromises()
    await w.find('.svg-pin.meal').trigger('click')
    const f = w.emitted('focus')![0]![0] as any
    expect(f).toEqual({ kind: 'meal', course: 0, cafe: 0 })
    await w.setProps({ focus: f })
    const card = w.find('.place-card')
    expect(card.text()).toContain('김치찌개 9,000원')
    expect(card.text()).toContain('확인 필요') // 영업시간
    expect(card.text()).toContain('예산 충족')
    expect(card.find('a').attributes('href')).toContain('map.kakao.com/link/search/')
  })

  it('카페 카드는 영업·편의시설을 확인 필요로 두고 이 카페로 코스 선택을 알린다', async () => {
    const recs = [makeRec({ cafes: threeCafes() })]
    const w = mount(MapPanel, { props: { recommendations: recs, selected: 0, focus: { kind: 'cafe', course: 0, cafe: 1 } } })
    await flushPromises()
    const card = w.find('.place-card.cafe')
    expect(card.text()).toContain('콘센트·와이파이 확인 필요')
    expect(card.text()).toContain('상세 링크 정보 없음') // 카페B 는 링크 없음
    await card.find('button.choose').trigger('click')
    expect(w.emitted('chooseCafe')![0]).toEqual([0, 1])
    await card.find('button.close').trigger('click')
    const focusEvents = w.emitted('focus')!
    expect(focusEvents[focusEvents.length - 1]).toEqual([null])
  })
})

describe('카페 바꾸기와 연결선', () => {
  it('선택한 코스의 다른 카페 후보를 보여 주고, 고른 카페로 연결선을 다시 그린다', async () => {
    const recs = [makeRec({ cafes: threeCafes() })]
    const w = mount(MapPanel, { props: { recommendations: recs, selected: 0 } })
    await flushPromises()
    expect(w.findAll('.svg-pin.alt')).toHaveLength(2)
    expect(w.find('.link text').text()).toBe('직선 45m')
    await w.setProps({ cafeChoice: { 0: 2 } })
    expect(w.find('.link text').text()).toBe('직선 210m')
    expect(w.find('.legend .link-note').text()).toContain('카페C까지')
  })

  it('카카오 지도에서도 고른 카페로 선을 다시 그리고 선택 코스로 범위를 맞춘다', async () => {
    const lines: any[] = []
    const bounds: any[] = []
    class LatLng { constructor(public lat: number, public lng: number) {} }
    ;(window as any).kakao = { maps: {
      LatLng,
      LatLngBounds: class { pts: any[] = []; extend(p: any) { this.pts.push(p) } },
      Map: class { setBounds(b: any) { bounds.push(b.pts.length) } relayout() {} },
      CustomOverlay: class { constructor(public opts: any) {} setMap() {} },
      Polyline: class { constructor(public opts: any) { lines.push(this) } setMap() {} },
    } }
    const recs = [makeRec({ cafes: threeCafes() }), makeRec({ name: '라멘', source_id: '6', latitude: 37.4995, longitude: 127.03 })]
    const w = mount(MapPanel, { props: { recommendations: recs, selected: 0 } })
    await flushPromises()
    await w.setProps({ cafeChoice: { 0: 2 } })
    await flushPromises()
    expect(lines[lines.length - 1].opts.path[1].lat).toBe(37.4970)
    expect(bounds[bounds.length - 1]).toBe(2) // 선택한 코스의 식당·카페 두 곳으로 범위 조정
  })
})

describe('카드 ↔ 지도 상태 연동 (공통 상태)', () => {
  it('카드에서 카페를 바꾸면 지도·타임라인·저장 요청이 같은 카페를 쓴다', async () => {
    const fetch = mockChat(() => makeResult({ recommendations: [makeRec({ cafes: threeCafes() }), makeRec({ name: '라멘가게', source_id: '6' })] }))
    const w = mount(ChatView, { global: { plugins: [makeRouter()] } })
    await w.find('form.composer input').setValue('강남역 점심')
    await w.find('form.composer').trigger('submit')
    await flushPromises()
    const card = w.findAll('article.rec')[0]!
    await card.findAll('details.more button')[1]!.trigger('click') // 카페C 로 바꾸기
    expect(courseState.cafeChoice[0]).toBe(2)
    expect(card.find('.main-cafe').text()).toContain('카페C')
    expect(w.find('.legend .link-note').text()).toContain('카페C까지')
    expect(w.findAll('.course-timeline .step')[2]!.text()).toContain('카페C')
    await card.find('button.save').trigger('click')
    await flushPromises()
    const bodies = fetch.mock.calls.filter(([u]) => u === '/api/chat/stream').map(([, i]) => JSON.parse(i!.body as string).message)
    expect(bodies[bodies.length - 1]).toBe('1번 코스 저장해줘 (카페 3번)')
  })

  it('지도에서 2번 코스 식당을 누르면 2번 카드가 강조되고 정보 카드가 열린다', async () => {
    mockChat(() => makeResult())
    const w = mount(ChatView, { global: { plugins: [makeRouter()] } })
    await w.find('form.composer input').setValue('강남역 점심')
    await w.find('form.composer').trigger('submit')
    await flushPromises()
    await w.findAll('.svg-pin.meal')[1]!.trigger('click')
    expect(courseState.selected).toBe(1)
    expect(w.findAll('.rec-wrap')[1]!.classes()).toContain('on')
    expect(w.find('.place-card h4').text()).toBe('라멘가게')
    await w.findAll('article.rec')[0]!.findAll('button.map-btn')[0]!.trigger('click') // 카드의 '지도에서 식당 보기'
    expect(courseState.selected).toBe(0)
    expect(w.find('.place-card h4').text()).toBe('김치찌개집')
  })
})

describe('지도를 쓸 수 없을 때', () => {
  it('좌표 위치도와 함께 장소 목록을 보여 주고, 좌표 없는 장소는 핀 없이 목록에만 둔다', async () => {
    const recs = [makeRec(), makeRec({ name: '좌표없음식당', source_id: '9', latitude: null, longitude: null })]
    const w = mount(MapPanel, { props: { recommendations: recs, selected: 0 } })
    await flushPromises()
    expect(w.text()).toContain('지도 키가 없어')
    const items = w.findAll('.place-list li').map((li) => li.text())
    expect(items).toHaveLength(2)
    expect(items[1]).toContain('좌표없음식당')
    expect(w.findAll('.svg-pin.meal')).toHaveLength(1)
  })
})

describe('저장한 코스 지도', () => {
  it('저장 당시 좌표가 있으면 식당·카페를 지도에 다시 표시하고, 없으면 이유를 안내한다', async () => {
    const plan = (id: number, coords: boolean) => ({
      id, title: `계획${id}`, plan_date: '2026-11-20', start_time: '12:00:00', end_time: '15:00:00', area: '강남역',
      restaurant_name: '김치찌개집', restaurant_source: 'seoul_tourism_redtable', restaurant_source_id: '1', restaurant_address: '주소',
      restaurant_lat: coords ? 37.4981 : null, restaurant_lng: coords ? 127.0277 : null,
      cafe_name: '카페1', cafe_source: 'k', cafe_source_id: 'k1', cafe_address: '카페주소', cafe_url: 'http://place.map.kakao.com/1',
      cafe_lat: coords ? 37.4984 : null, cafe_lng: coords ? 127.0280 : null, memo: null, session_id: null,
      created_at: '2026-11-19T10:00:00+09:00', updated_at: '2026-11-19T10:00:00+09:00' })
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ plans: [plan(1, true), plan(2, false)] }) })))
    const router = makeRouter()
    router.push('/plans/1')
    await router.isReady()
    const w = mount(PlansView, { global: { plugins: [router] } })
    await flushPromises()
    expect(w.find('.plan-map').exists()).toBe(true)
    expect(w.findAll('.plan-map .svg-pin.meal')).toHaveLength(1)
    expect(w.findAll('.plan-map .svg-pin.cafe')).toHaveLength(1)
    expect(w.find('.plan-map .link text').text()).toContain('직선')
    await router.push('/plans/2')
    await flushPromises()
    expect(w.find('.plan-map').exists()).toBe(false)
    expect(w.text()).toContain('저장 당시 좌표가 없어')
  })
})

describe('출구 기준 (N번 출구 근처)', () => {
  const origin = { kind: 'exit' as const, label: '강남역 11번 출구', latitude: 37.4990, longitude: 127.0262, source: "카카오 로컬 '강남역 2호선 11번출구'" }

  it('기준 출구를 지도에 표시하고 거리 문구도 출구 기준으로 쓴다', async () => {
    const recs = [makeRec({ distance_from: '강남역 11번 출구', distance_m: 120 })]
    const w = mount(MapPanel, { props: { recommendations: recs, selected: 0, origin, focus: { kind: 'meal', course: 0, cafe: 0 } } })
    await flushPromises()
    expect(w.findAll('.svg-pin.exit')).toHaveLength(1)
    expect(w.find('.svg-pin.exit .station-label').text()).toBe('강남역 11번 출구')
    expect(w.find('.legend .origin-note').text()).toBe('거리 기준: 강남역 11번 출구')
    expect(w.find('.place-card').text()).toContain('강남역 11번 출구에서 직선 120m')
  })

  it('역 중심 기준이면 출구 핀을 그리지 않는다', async () => {
    const w = mount(MapPanel, { props: { recommendations: [makeRec()], selected: 0, origin: { ...origin, kind: 'station' as const, label: '강남역' } } })
    await flushPromises()
    expect(w.findAll('.svg-pin.exit')).toHaveLength(0)
    expect(w.find('.legend .origin-note').exists()).toBe(false)
  })

  it('추천 카드의 거리도 기준점 이름으로 표시한다', async () => {
    mockChat(() => makeResult({ origin, recommendations: [makeRec({ distance_from: '강남역 11번 출구', distance_m: 88 })] }))
    const w = mount(ChatView, { global: { plugins: [makeRouter()] } })
    await w.find('form.composer input').setValue('강남역 11번 출구 근처 점심')
    await w.find('form.composer').trigger('submit')
    await flushPromises()
    expect(w.find('article.rec').text()).toContain('강남역 11번 출구에서 직선 88m')
    expect(w.findAll('aside.mapside .svg-pin.exit')).toHaveLength(1)
  })
})

describe('역 기준점 핀', () => {
  it('응답 기준점이 역이면 그 좌표에 역 핀을 그린다 (기본 두 역이 아니어도)', async () => {
    const origin = { kind: 'station' as const, label: '선릉역', latitude: 37.504571, longitude: 127.048505, source: '서울시 역사마스터 정보' }
    const w = mount(MapPanel, { props: { recommendations: [makeRec({ area: '선릉역', latitude: 37.5050, longitude: 127.0480 })], selected: 0, origin } })
    await flushPromises()
    expect(w.findAll('.svg-pin.station .station-label').map((t) => t.text())).toEqual(['선릉역'])
  })
})
