// UI 개선 4 — 식사 → 이동 → 카공 시작 타임라인
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import CourseTimeline from '../src/components/CourseTimeline.vue'
import { makeRec } from './helpers'

const texts = (w: ReturnType<typeof mount>) => w.findAll('.step').map((s) => s.text())

describe('코스 타임라인', () => {
  it('요청한 식사 시각과 확인된 거리·도보 추정만 쓰고 카공 시각은 만들지 않는다', () => {
    const w = mount(CourseTimeline, { props: { rec: makeRec(), index: 0,
      conditions: { base: { meal_time: '12:00:00', meal_period: '점심', cafe_time: null } } } })
    const [meal, walk, study] = texts(w)
    expect(meal).toContain('12:00')
    expect(meal).toContain('영업 매일 11:00~21:00')
    expect(walk).toContain('직선 45m')
    expect(walk).toContain('도보 약 1분 (직선거리 기준 추정)')
    expect(study).toContain('식사 후')
    expect(study).not.toMatch(/1[2-9]:\d\d/) // 식사 시간을 가정해 카공 시각을 계산하지 않음
    expect(study).toContain('카페 영업시간 미확인')
  })

  it('사용자가 말한 카페 시각·종료 시각은 그대로 쓴다', () => {
    const w = mount(CourseTimeline, { props: { rec: makeRec(), index: 1,
      conditions: { base: { meal_time: '12:30:00', cafe_time: '14:00:00' }, constraint: { end_by: '18:00:00' } } } })
    expect(texts(w)[2]).toContain('14:00')
    expect(texts(w)[2]).toContain('18:00까지')
    expect(w.find('h3').text()).toBe('2번 코스 흐름')
  })

  it('시각·영업시간·카페가 없으면 미지정·미확인으로 둔다', () => {
    const w = mount(CourseTimeline, { props: { rec: makeRec({ business_hours: null, cafes: [] }), index: 0,
      conditions: { base: { meal_period: '저녁' } } } })
    const [meal, walk, study] = texts(w)
    expect(meal).toContain('저녁 · 시각 미지정')
    expect(meal).toContain('영업시간 미확인')
    expect(walk).toContain('거리 미확인')
    expect(study).toContain('카페 미정')
    expect(w.findAll('.step.known')).toHaveLength(0)
  })
})
