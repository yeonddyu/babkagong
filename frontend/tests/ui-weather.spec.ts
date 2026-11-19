// UI 개선 6 — 날씨 반응형 UI (UI-04 에서 날씨 띠는 마스코트로 합침)
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import WeatherMascot from '../src/components/WeatherMascot.vue'
import ChatView from '../src/views/ChatView.vue'
import { weatherMood } from '../src/utils/weather'
import { makeResult, makeRouter, mockChat } from './helpers'

afterEach(() => vi.unstubAllGlobals())

describe('날씨 분위기 판정 (백엔드 정책과 같은 기준)', () => {
  it.each([
    [{ precipitation_type: '비', precipitation_probability: 80, temperature_c: 10 }, 'rain'],
    [{ precipitation_type: '없음', precipitation_probability: 60, temperature_c: 10 }, 'rain'],
    [{ precipitation_type: '눈', precipitation_probability: 70, temperature_c: -2 }, 'snow'],
    [{ precipitation_type: '없음', precipitation_probability: 10, temperature_c: 5 }, 'cold'],
    [{ precipitation_type: '없음', precipitation_probability: 0, temperature_c: 28 }, 'hot'],
    [{ precipitation_type: '없음', precipitation_probability: 0, temperature_c: 15, sky: '맑음' }, 'clear'],
    [{ precipitation_type: '없음', precipitation_probability: 30, temperature_c: 15, sky: '흐림' }, 'cloudy'],
  ])('%o → %s', (w, mood) => {
    expect(weatherMood(w)).toBe(mood)
  })

  it('날씨 응답이 없으면 분위기를 정하지 않는다', () => {
    expect(weatherMood(null)).toBeNull()
  })
})

describe('마스코트의 날씨 정보', () => {
  it('기상청 출처·예보 시각과 추천에 반영한 날씨 정책을 보여 준다', () => {
    const w = mount(WeatherMascot, { props: { hasResult: true,
      weather: { forecast_datetime: '2026-11-19T12:00:00+09:00', temperature_c: 9, precipitation_probability: 80, precipitation_type: '비' },
      policy: ['강수확률 80% / 비 → 가까운 식당·카페 우선'] } })
    expect(w.find('.tag').text()).toBe('11/19 12:00 예보')
    expect(w.text()).toContain('9°C · 강수확률 80% · 강수형태 비')
    expect(w.text()).toContain('기상청 단기예보 기준')
    expect(w.find('.policy').text()).toContain('가까운 식당·카페 우선')
  })

  it('없는 값은 미확인으로 표시한다', () => {
    const w = mount(WeatherMascot, { props: { hasResult: true, weather: { forecast_datetime: '2026-11-19T12:00:00+09:00', temperature_c: 3,
      precipitation_probability: null, precipitation_type: null } } })
    expect(w.text()).toContain('강수확률 미확인')
    expect(w.text()).toContain('강수형태 미확인')
  })

  it('대화 화면 전체에 날씨 상태가 반영된다', async () => {
    mockChat(() => makeResult({ weather: { forecast_datetime: '2026-11-19T12:00:00+09:00', temperature_c: 2,
      precipitation_probability: 10, precipitation_type: '없음', sky: '맑음' } }))
    const w = mount(ChatView, { global: { plugins: [makeRouter()] } })
    expect(w.find('.workspace').attributes('data-weather')).toBe('none')
    await w.find('input').setValue('강남역 점심')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.find('.workspace').attributes('data-weather')).toBe('cold')
    expect(w.find('.mascot').attributes('data-state')).toBe('cold')
  })
})
