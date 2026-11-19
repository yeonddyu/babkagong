// UI 개선 2 — 추천 지도 (카카오 SDK 는 가짜 객체로 대체, 키가 없을 때는 좌표 위치도)
/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import MapPanel from '../src/components/MapPanel.vue'
import { haversineM } from '../src/utils/kakaoMap'
import { makeResult } from './helpers'

const recs = makeResult().recommendations

afterEach(() => {
  delete (window as any).kakao
  vi.unstubAllGlobals()
})

describe('좌표 위치도 (지도 키 없음)', () => {
  it('식당·카페·역 핀을 실제 좌표로 그리고 선택한 코스만 직선으로 잇는다', async () => {
    const w = mount(MapPanel, { props: { recommendations: recs, selected: 1 } })
    await flushPromises()
    expect(w.find('svg.mini-map').exists()).toBe(true)
    expect(w.findAll('.svg-pin.meal')).toHaveLength(2)
    expect(w.findAll('.svg-pin.cafe')).toHaveLength(2)
    expect(w.findAll('.svg-pin.station')).toHaveLength(1)
    expect(w.findAll('.svg-pin.on')).toHaveLength(2) // 2번 코스의 식당·카페
    expect(w.find('.link text').text()).toBe('직선 60m') // 카카오가 준 거리 그대로
    expect(w.text()).toContain('실제 경로 아님')
    expect(w.text()).toContain('좌표로 그린 위치도')
  })

  it('핀을 누르면 그 코스를 선택한다', async () => {
    const w = mount(MapPanel, { props: { recommendations: recs, selected: 0 } })
    await flushPromises()
    await w.findAll('.svg-pin.meal')[1]!.trigger('click')
    expect(w.emitted('select')?.[0]).toEqual([1])
  })

  it('좌표가 없는 카페는 선을 그리지 않는다', async () => {
    const noCoord = [{ ...recs[0]!, cafes: [{ ...recs[0]!.cafes[0]!, latitude: null, longitude: null }] }]
    const w = mount(MapPanel, { props: { recommendations: noCoord, selected: 0 } })
    await flushPromises()
    expect(w.find('.link').exists()).toBe(false)
    expect(w.findAll('.svg-pin.cafe')).toHaveLength(0)
  })
})

describe('카카오 지도', () => {
  it('SDK 가 있으면 카카오 지도에 핀과 점선 직선을 그린다', async () => {
    const overlays: any[] = []
    const lines: any[] = []
    class LatLng { constructor(public lat: number, public lng: number) {} }
    ;(window as any).kakao = { maps: {
      LatLng,
      LatLngBounds: class { pts: any[] = []; extend(p: any) { this.pts.push(p) } },
      Map: class { bounds: any; relayouts = 0; setBounds(b: any) { this.bounds = b } relayout() { this.relayouts++ } },
      CustomOverlay: class { constructor(public opts: any) { overlays.push(this) } setMap() {} },
      Polyline: class { constructor(public opts: any) { lines.push(this) } setMap() {} },
    } }
    const w = mount(MapPanel, { props: { recommendations: recs, selected: 0 } })
    await flushPromises()
    expect(w.find('svg.mini-map').exists()).toBe(false)
    expect(overlays).toHaveLength(5) // 식당 2 + 카페 2 + 역 1 (위치가 모두 다름)
    expect(lines).toHaveLength(1)
    expect(lines[0].opts.strokeStyle).toBe('shortdash')
    expect(lines[0].opts.path[0].lat).toBe(recs[0]!.latitude)
    expect(lines[0].opts.path[1].lat).toBe(recs[0]!.cafes[0]!.latitude)
    expect(overlays[0].opts.content.className).toContain('on')
  })
})

it('같은 위치의 식당·카페는 하나의 핀으로 묶고 위치를 옮기지 않는다', async () => {
  const same = [recs[0]!, { ...recs[1]!, latitude: recs[0]!.latitude, longitude: recs[0]!.longitude, cafes: recs[0]!.cafes }]
  const w = mount(MapPanel, { props: { recommendations: same, selected: 1 } })
  await flushPromises()
  const meals = w.findAll('.svg-pin.meal')
  expect(meals).toHaveLength(1)
  expect(meals[0]!.text()).toContain('1·2')
  expect(meals[0]!.classes()).toContain('on')
  expect(w.findAll('.svg-pin.cafe')).toHaveLength(1)
  await meals[0]!.trigger('click')
  expect(w.emitted('select')?.[0]).toEqual([0]) // 겹친 핀을 누르면 다른 코스로 전환
})

it('식당과 카페가 같은 건물이면 선 대신 같은 위치로 표기하고 카페를 배지로 붙인다', async () => {
  const r = recs[0]!
  const same = [{ ...r, cafes: [{ ...r.cafes[0]!, latitude: r.latitude, longitude: r.longitude, distance_m: 0 }] }]
  const w = mount(MapPanel, { props: { recommendations: same, selected: 0 } })
  await flushPromises()
  expect(w.find('.link line').exists()).toBe(false)
  expect(w.find('.link text').text()).toBe('같은 위치 · 직선 0m')
  expect(w.find('.svg-pin.cafe').classes()).toContain('attached')
})

it('직선거리 계산', () => {
  expect(Math.round(haversineM([37.497952, 127.027619], [37.500622, 127.036456]))).toBeGreaterThan(800)
})

it('키가 있는데 지도를 불러오지 못하면 도메인 등록을 안내한다', async () => {
  vi.stubEnv('VITE_KAKAO_MAP_KEY', 'test-js-key')
  const real = document.head.appendChild.bind(document.head)
  vi.spyOn(document.head, 'appendChild').mockImplementation((node: any) => {
    const r = real(node)
    if (node.tagName === 'SCRIPT') setTimeout(() => node.onerror?.(new Event('error')))
    return r
  })
  const w = mount(MapPanel, { props: { recommendations: recs, selected: 0 } })
  await new Promise((r) => setTimeout(r, 10))
  await flushPromises()
  expect(w.text()).toContain('Web 도메인 등록을 확인')
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})
