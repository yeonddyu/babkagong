// UI 개선 6 — 날씨 반응형 UI
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import WeatherStrip from '../src/components/WeatherStrip.vue'
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

  it('날씨 응답이 없으면 꾸미지 않는다', () => {
    expect(weatherMood(null)).toBeNull()
    const w = mount(WeatherStrip, { props: { weather: null, policy: ['날씨 미확인 → 기본 정책'] } })
    expect(w.find('.weather').exists()).toBe(false)
  })
})

describe('날씨 띠', () => {
  it('비 예보면 빗방울 효과와 기상청 출처·적용 정책을 보여 준다', () => {
    const w = mount(WeatherStrip, { props: {
      weather: { forecast_datetime: '2026-11-19T12:00:00+09:00', temperature_c: 9, precipitation_probability: 80, precipitation_type: '비' },
      policy: ['강수확률 80% / 비 → 가까운 식당·카페 우선'] } })
    expect(w.find('.weather').classes()).toContain('mood-rain')
    expect(w.findAll('.fx i')).toHaveLength(12)
    expect(w.text()).toContain('비 소식이 있어요')
    expect(w.text()).toContain('9°C · 강수확률 80% · 비')
    expect(w.text()).toContain('11/19 12:00 예보 · 기상청 단기예보')
    expect(w.text()).toContain('가까운 식당·카페 우선')
  })

  it('없는 값은 미확인으로 표시한다', () => {
    const w = mount(WeatherStrip, { props: { weather: { forecast_datetime: '2026-11-19T12:00:00+09:00', temperature_c: 3,
      precipitation_probability: null, precipitation_type: null }, policy: [] } })
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
    expect(w.find('.weather').text()).toContain('쌀쌀한 날이에요')
  })
})
