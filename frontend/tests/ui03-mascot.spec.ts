// UI-03 날씨 반응형 마스코트
import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import WeatherMascot from '../src/components/WeatherMascot.vue'
import ChatView from '../src/views/ChatView.vue'
import { mascotState } from '../src/utils/weather'
import { makeResult, makeRouter, mockChat } from './helpers'

const wx = (o: Record<string, any> = {}) => ({
  forecast_datetime: '2026-11-20T12:00:00+09:00', base_datetime: '2026-11-20T08:00:00+09:00',
  temperature_c: 15, precipitation_probability: 20, precipitation_type: '없음', sky: '맑음', default_applied: [], notes: [], ...o })

describe('마스코트 상태 판정 (정책 기준과 같은 값)', () => {
  it.each([
    [wx({ temperature_c: 5 }), 'cold'],
    [wx({ temperature_c: 6 }), 'clear'],
    [wx({ temperature_c: 28 }), 'hot'],
    [wx({ precipitation_type: '비' }), 'rain'],
    [wx({ precipitation_type: '소나기', temperature_c: 2 }), 'rain'],
    [wx({ precipitation_probability: 60 }), 'rain-maybe'],
    [wx({ precipitation_probability: 59, sky: '흐림' }), 'mild'],
    [wx({ precipitation_type: '눈', temperature_c: -2 }), 'snow'],
  ])('%o → %s', (w, expected) => {
    expect(mascotState(w, true)).toBe(expected)
  })

  it('응답 전에는 대기, 응답에 날씨가 없으면 중립 상태', () => {
    expect(mascotState(null, false)).toBe('idle')
    expect(mascotState(null, true)).toBe('neutral')
    expect(mascotState({ temperature_c: null, precipitation_probability: null, sky: null, precipitation_type: null }, true)).toBe('neutral')
  })
})

describe('마스코트 화면', () => {
  it('비 예보는 우산을 펴고, 강수확률만 높으면 "비 올 수도"로 구분해 안내한다', () => {
    const rain = mount(WeatherMascot, { props: { weather: wx({ precipitation_type: '비', precipitation_probability: 80 }), hasResult: true } })
    expect(rain.find('.umbrella').exists()).toBe(true)
    expect(rain.find('.bubble').text()).toBe('비 예보가 있어요. 우산 챙겨 가요!')
    const maybe = mount(WeatherMascot, { props: { weather: wx({ precipitation_probability: 70 }), hasResult: true } })
    expect(maybe.find('.umbrella').exists()).toBe(false)
    expect(maybe.find('.umbrella-closed').exists()).toBe(true)
    expect(maybe.find('.bubble').text()).toBe('강수확률 70%예요. 비가 올 수도 있어요')
    expect(maybe.text()).toContain('실제 비가 온다는 뜻은 아니에요')
  })

  it('추움·더움 상태의 소품과 대사를 보여 준다', () => {
    const cold = mount(WeatherMascot, { props: { weather: wx({ temperature_c: 1 }), hasResult: true } })
    expect(cold.find('.scarf').exists()).toBe(true)
    expect(cold.find('.steam').exists()).toBe(true)
    expect(cold.find('.bubble').text()).toContain('따뜻한 국물')
    const hot = mount(WeatherMascot, { props: { weather: wx({ temperature_c: 31 }), hasResult: true } })
    expect(hot.find('.fan').exists()).toBe(true)
    expect(hot.find('svg').attributes('aria-label')).toBe('밥알이: 더움')
  })

  it('값은 방문 시각 예보로 표시하고 실측이 아니라고 밝힌다', () => {
    const w = mount(WeatherMascot, { props: { weather: wx({ temperature_c: 12.5 }), hasResult: true } })
    expect(w.find('.tag').text()).toBe('11/20 12:00 예보')
    expect(w.find('.facts').text()).toContain('12.5°C · 강수확률 20% · 강수형태 없음')
    expect(w.text()).toContain('실측값 아님')
  })

  it('날씨를 확인하지 못하면 중립 표정으로 안내하고 수치를 만들지 않는다', () => {
    const w = mount(WeatherMascot, { props: { weather: null, hasResult: true } })
    expect(w.attributes('data-state')).toBe('neutral')
    expect(w.find('.bubble').text()).toBe('날씨 정보를 확인할 수 없어요')
    expect(w.find('.facts').exists()).toBe(false)
    expect(w.text()).not.toContain('°C')
  })
})

describe('대화 화면 연동 (새 API 호출 없음)', () => {
  it('추천 응답의 날씨로 마스코트가 바뀌고 날씨 API 를 따로 부르지 않는다', async () => {
    const fetch = mockChat(() => makeResult({ weather: wx({ precipitation_type: '비', precipitation_probability: 90 }) }))
    const w = mount(ChatView, { global: { plugins: [makeRouter()] } })
    expect(w.find('.mascot').attributes('data-state')).toBe('idle')
    await w.find('input').setValue('강남역 점심')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.find('.mascot').attributes('data-state')).toBe('rain')
    expect(fetch.mock.calls.map(([u]) => String(u)).every((u) => !u.includes('weather'))).toBe(true)
  })
})
