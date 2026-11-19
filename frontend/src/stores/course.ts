// 추천 코스 공통 상태: 선택한 코스, 코스별로 고른 카페, 지도·카드에서 눌러 본 장소.
// 지도·추천 카드·타임라인·룰렛·저장 버튼이 모두 이 상태만 읽고 바꿔 서로 어긋나지 않게 한다.
import { reactive, readonly } from 'vue'
import type { Cafe, Recommendation } from '../types'

export interface Focus { kind: 'meal' | 'cafe'; course: number; cafe: number }

const state = reactive({
  selected: 0,
  cafeChoice: {} as Record<number, number>,
  focus: null as Focus | null,
})

export const courseState = readonly(state)

export function resetCourse() {
  state.selected = 0
  state.cafeChoice = {}
  state.focus = null
}

export function selectCourse(index: number) {
  state.selected = index
}

export function chosenCafeIndex(course: number): number {
  return state.cafeChoice[course] ?? 0
}

export function chosenCafe(rec: Recommendation | undefined, course: number): Cafe | null {
  if (!rec) return null
  return rec.cafes[chosenCafeIndex(course)] ?? rec.cafes[0] ?? null
}

/** 코스의 카페를 바꾼다. 그 코스를 선택하고 지도 연결선·저장 대상도 바뀐다. */
export function chooseCafe(course: number, cafe: number) {
  state.cafeChoice = { ...state.cafeChoice, [course]: cafe }
  state.selected = course
  if (state.focus?.kind === 'cafe' && state.focus.course === course) state.focus = { kind: 'cafe', course, cafe }
}

/** 지도 마커나 카드의 '지도 보기'로 장소를 열어 본다. 해당 코스도 선택된다. */
export function focusPlace(f: Focus | null) {
  state.focus = f
  if (f) state.selected = f.course
}
