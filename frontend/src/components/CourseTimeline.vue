<script setup lang="ts">
// 선택한 코스의 식사 → 이동 → 카공 시작. 사용자가 말한 시각과 확인된 거리·도보 추정만 쓴다.
// 식사에 걸리는 시간은 알 수 없으므로 카공 시작 시각을 계산해 만들지 않는다.
import { computed } from 'vue'
import type { Recommendation } from '../types'

const props = defineProps<{ rec: Recommendation; index: number; conditions: Record<string, any> }>()

const hhmm = (t: unknown) => (typeof t === 'string' && /^\d{2}:\d{2}/.test(t) ? t.slice(0, 5) : null)
const base = computed(() => props.conditions?.base ?? {})
const endBy = computed(() => hhmm(props.conditions?.constraint?.end_by))
const cafe = computed(() => props.rec.cafes[0] ?? null)

const steps = computed(() => {
  const mealTime = hhmm(base.value.meal_time)
  const period = base.value.meal_period as string | null
  const cafeTime = hhmm(base.value.cafe_time)
  return [
    {
      key: 'meal', icon: '🍚', label: '식사',
      time: mealTime ?? (period ? `${period} · 시각 미지정` : '시각 미지정'),
      known: Boolean(mealTime),
      place: props.rec.name,
      note: props.rec.business_hours ? `영업 ${props.rec.business_hours}` : '영업시간 미확인',
    },
    {
      key: 'walk', icon: '🚶', label: '카페로 이동',
      time: cafe.value?.distance_m != null ? `직선 ${cafe.value.distance_m}m` : '거리 미확인',
      known: cafe.value?.distance_m != null,
      place: cafe.value?.estimated_walk_minutes ? `도보 약 ${cafe.value.estimated_walk_minutes}분 (직선거리 기준 추정)` : '도보 시간 미확인',
      note: '실제 경로 시간이 아니에요',
    },
    {
      key: 'study', icon: '☕', label: '카공 시작',
      time: cafeTime ?? '식사 후',
      known: Boolean(cafeTime),
      place: cafe.value?.name ?? '카페 미정',
      note: endBy.value ? `${endBy.value}까지 · 카페 영업시간 미확인` : '카페 영업시간 미확인',
    },
  ]
})
</script>

<template>
  <section class="course-timeline card" :aria-label="`${index + 1}번 코스 일정`">
    <h3>{{ index + 1 }}번 코스 흐름</h3>
    <ol :key="rec.source + rec.source_id" class="track">
      <li v-for="(s, i) in steps" :key="s.key" :class="['step', s.key, { known: s.known }]" :style="{ '--i': i }">
        <span class="node" aria-hidden="true">{{ s.icon }}</span>
        <div class="body">
          <span class="label">{{ s.label }}</span>
          <strong class="time">{{ s.time }}</strong>
          <span class="place">{{ s.place }}</span>
          <span class="note small muted">{{ s.note }}</span>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.course-timeline { border-radius: 22px; padding: 16px 18px; }
h3 { margin: 0 0 12px; font-family: 'Gowun Dodum', sans-serif; font-size: 17px; }
.track { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; position: relative; }
.track::before { content: ''; position: absolute; left: 22px; right: 22px; top: 21px; border-top: 3px dashed var(--line); }
.step { position: relative; display: flex; flex-direction: column; gap: 8px; animation: rise .35s ease both; animation-delay: calc(var(--i) * 80ms); }
.node { width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; font-size: 20px; background: #fff;
  border: 3px solid var(--line); position: relative; z-index: 1; }
.step.meal .node { border-color: var(--accent); }
.step.study .node { border-color: var(--coffee); }
.body { display: flex; flex-direction: column; gap: 2px; }
.label { font-size: 12px; color: var(--muted); }
.time { font-size: 16px; }
.step:not(.known) .time { color: var(--warn); font-weight: 500; }
.place { font-size: 14px; }
@keyframes rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .step { animation: none; } }
@media (max-width: 600px) {
  .track { grid-template-columns: 1fr; }
  .track::before { left: 21px; right: auto; top: 22px; bottom: 22px; border-top: none; border-left: 3px dashed var(--line); }
  .step { flex-direction: row; align-items: flex-start; }
}
</style>
