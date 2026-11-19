<script setup lang="ts">
// 왼쪽 열의 추천 영역: 가장 최근 추천 결과의 룰렛·코스 흐름·식당/카페 카드. 지도는 오른쪽 열(ChatView)에 있고 공통 상태로 연동된다.
import CourseTimeline from './CourseTimeline.vue'
import MenuRoulette from './MenuRoulette.vue'
import RecommendationCard from './RecommendationCard.vue'
import { chooseCafe, courseState, focusPlace, selectCourse } from '../stores/course'
import type { ChatResponse } from '../types'

defineProps<{ result: ChatResponse | null; selected: number; savingIndex: number | null; busy: boolean }>()
const emit = defineEmits<{ select: [index: number]; save: [index: number]; more: []; showMap: [] }>()
function select(i: number) {
  selectCourse(i)
  emit('select', i)
}
// 룰렛 결과를 기존 추천 코스로 연결: 그 코스를 고르고 지도에서 식당 정보 카드를 연다
function pickFromRoulette(i: number) {
  select(i)
  focusPlace({ kind: 'meal', course: i, cafe: courseState.cafeChoice[i] ?? 0 })
}
function locate(i: number) {
  pickFromRoulette(i)
  emit('showMap') // 모바일은 지도 탭으로 전환 (데스크톱은 오른쪽 지도가 항상 보임)
}
</script>

<template>
  <section v-if="result" class="course-panel" aria-label="추천 코스">
    <div v-if="!result.recommendations.length" class="empty card">
      <p class="empty-title">조건에 맞는 코스를 찾지 못했어요</p>
      <p v-if="result.stop_reason" class="small">{{ result.stop_reason }}</p>
      <ul v-if="result.suggestions.length" class="small">
        <li v-for="s in result.suggestions" :key="s">{{ s }}</li>
      </ul>
    </div>
    <template v-else>
      <MenuRoulette :recommendations="result.recommendations" @select="pickFromRoulette" @locate="locate" />
      <CourseTimeline v-if="result.recommendations[selected]" :rec="result.recommendations[selected]!" :index="selected"
                      :cafe-index="courseState.cafeChoice[selected] ?? 0" :conditions="result.conditions" />
      <div class="recs-head">
        <h2>추천 코스 {{ result.recommendations.length }}곳</h2>
        <p v-if="result.more" class="more-note small">앞서 보여 드린 곳은 빼고 같은 조건으로 다시 골랐어요</p>
      </div>
      <div class="recs">
        <div v-for="(r, ri) in result.recommendations" :key="r.source + r.source_id" :id="`course-${ri}`"
             class="rec-wrap" :class="{ on: selected === ri }" :style="{ '--i': ri }" @click="select(ri)">
          <RecommendationCard :rec="r" :index="ri" :saving="busy && savingIndex === ri" :cafe-index="courseState.cafeChoice[ri] ?? 0"
                              @save="$emit('save', $event)" @choose-cafe="chooseCafe" @focus="focusPlace" />
        </div>
      </div>
      <button class="btn more-btn" :disabled="busy" @click="$emit('more')">
        {{ busy ? '찾는 중…' : '다른 곳 더 보기' }}
      </button>
    </template>
    <details v-if="result.criteria.length || result.excluded.length" class="card small basis">
      <summary>판단 기준과 제외한 후보 ({{ result.excluded.length }})</summary>
      <ul><li v-for="c in result.criteria" :key="c">{{ c }}</li></ul>
      <ul v-if="result.weather_policy.length"><li v-for="w in result.weather_policy" :key="w">날씨 반영: {{ w }}</li></ul>
      <ul class="excluded"><li v-for="x in result.excluded" :key="x.source + x.source_id"><b>{{ x.name }}</b> — {{ x.reason }}</li></ul>
    </details>
  </section>
</template>

<style scoped>
.course-panel { display: flex; flex-direction: column; gap: 14px; }
.empty { text-align: left; padding: 24px; }
.empty-title { font-family: 'Gowun Dodum', sans-serif; font-size: 20px; margin: 0 0 6px; }
.recs-head h2 { margin: 4px 0 0; font-family: 'Gowun Dodum', sans-serif; font-size: 20px; }
.recs { display: grid; gap: 14px; }
.rec-wrap { border-radius: 22px; outline: 3px solid transparent; outline-offset: 2px; cursor: pointer; scroll-margin-top: 80px;
  transition: outline-color .2s, transform .2s, box-shadow .2s; animation: cardIn .4s ease both; animation-delay: calc(var(--i) * 60ms); }
.rec-wrap:hover { transform: translateY(-2px); box-shadow: 0 10px 24px -16px rgba(80, 50, 20, .45); }
.rec-wrap.on { outline-color: var(--accent); }
@keyframes cardIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .rec-wrap { animation: none; transition: outline-color .2s; } .rec-wrap:hover { transform: none; } }
.more-btn { align-self: center; border-radius: 999px; padding: 10px 22px; background: #fff; border: 2px dashed var(--accent); color: var(--accent); font-weight: 700; }
.more-btn:disabled { opacity: .6; }
.more-note { margin: 0; color: var(--accent); }
.basis summary { cursor: pointer; font-weight: 500; }
.basis ul { margin: 8px 0; padding-left: 18px; }
.excluded { color: var(--muted); }
</style>
