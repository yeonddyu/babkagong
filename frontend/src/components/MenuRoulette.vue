<script setup lang="ts">
// 오늘 뭐 먹지? 원형 메뉴 룰렛.
// 후보는 Agent 가 조건(예산·제외 음식·영업)을 통과시킨 추천 코스의 메뉴만 쓴다:
//   예산 조건이 있으면 예산 안 메뉴, 없으면 가격이 확인된 대표 메뉴. 2개 미만이면 추천 식당 뽑기로 바꾼다.
// 메뉴·가격·식당을 지어내지 않는다. 결과는 기존 추천 코스(지도·카드)로 연결된다.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { Recommendation } from '../types'

const props = withDefaults(defineProps<{ recommendations: Recommendation[]; random?: () => number; spinMs?: number }>(), {
  random: () => Math.random(),
  spinMs: 3200,
})
const emit = defineEmits<{ select: [index: number]; locate: [index: number] }>()

const MAX_SLICES = 10
const COLORS = ['#f6c9a8', '#fbe3d4', '#efd2b8', '#fff1e3', '#f3b98f', '#fde8d6', '#e9c4a2', '#fff6ec', '#f7d3b7', '#f2dccb']

interface Slot { menu: string | null; price: number | null; course: number; restaurant: string; reason: string }
const reasonOf = (r: Recommendation) => {
  const pass = r.checks.filter((c) => c.result === 'pass').map((c) => `${c.criterion} 충족`)
  if (r.distance_m != null) pass.unshift(`역에서 직선 ${r.distance_m}m`)
  return pass.join(' · ') || '조건을 통과한 추천 코스'
}
const menuSlots = computed<Slot[]>(() =>
  props.recommendations.flatMap((r, i) => {
    const menus = r.matched_menus.length ? r.matched_menus : r.sample_menus ?? []
    return menus.filter((m) => m.price_krw).map((m) => ({ menu: m.name, price: m.price_krw!, course: i, restaurant: r.name, reason: reasonOf(r) }))
  }))
const mode = computed<'menu' | 'restaurant' | 'none'>(() =>
  menuSlots.value.length >= 2 ? 'menu' : props.recommendations.length >= 2 ? 'restaurant' : 'none')
// 코스마다 돌아가며 골라 원판에 올린다 (한 식당 메뉴로만 채워지지 않게)
const slots = computed<Slot[]>(() => {
  if (mode.value !== 'menu') {
    return props.recommendations.slice(0, MAX_SLICES).map((r, i) => ({ menu: null, price: null, course: i, restaurant: r.name, reason: reasonOf(r) }))
  }
  const byCourse = new Map<number, Slot[]>()
  menuSlots.value.forEach((s) => byCourse.set(s.course, [...(byCourse.get(s.course) ?? []), s]))
  const out: Slot[] = []
  for (let round = 0; out.length < MAX_SLICES; round++) {
    let added = false
    for (const list of byCourse.values()) {
      if (list[round] && out.length < MAX_SLICES) { out.push(list[round]!); added = true }
    }
    if (!added) break
  }
  return out
})

const angle = ref(0)
const spinning = ref(false)
const result = ref<Slot | null>(null)
let timer: ReturnType<typeof setTimeout> | null = null
watch(slots, () => { result.value = null; angle.value = 0 })
onBeforeUnmount(() => { if (timer) clearTimeout(timer) })

const step = computed(() => 360 / Math.max(slots.value.length, 1))
function reducedMotion() {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function spin() {
  if (spinning.value || slots.value.length < 2) return
  const index = Math.min(slots.value.length - 1, Math.floor(props.random() * slots.value.length))
  // 바늘(위쪽)이 고른 칸 가운데에 오도록 회전 (현재 각도에서 5바퀴 이상 더 돌림)
  const target = 360 - (index * step.value + step.value / 2)
  const base = angle.value - (angle.value % 360)
  angle.value = base + 360 * 5 + target
  result.value = null
  const instant = props.spinMs <= 0 || reducedMotion()
  spinning.value = !instant
  const done = () => { spinning.value = false; result.value = slots.value[index]! }
  if (instant) done()
  else timer = setTimeout(done, props.spinMs)
}

// 원판 칸 그리기
const R = 120
function slicePath(i: number) {
  const a0 = (i * step.value - 90) * Math.PI / 180
  const a1 = ((i + 1) * step.value - 90) * Math.PI / 180
  const large = step.value > 180 ? 1 : 0
  return `M0 0 L${R * Math.cos(a0)} ${R * Math.sin(a0)} A${R} ${R} 0 ${large} 1 ${R * Math.cos(a1)} ${R * Math.sin(a1)} Z`
}
function labelTransform(i: number) {
  const mid = i * step.value + step.value / 2
  return `rotate(${mid - 90}) translate(${R * 0.58} 0) rotate(${mid > 180 ? 180 : 0})`
}
const short = (s: string) => (s.length > 9 ? `${s.slice(0, 8)}…` : s)
const won = (v: number) => `${v.toLocaleString()}원`
</script>

<template>
  <section v-if="recommendations.length" class="roulette card" :class="`mode-${mode}`" aria-label="오늘 뭐 먹지 룰렛">
    <header class="head">
      <h3>{{ mode === 'restaurant' ? '오늘 뭐 먹지? 식당 뽑기' : '오늘 뭐 먹지?' }}</h3>
      <p class="muted small">
        <template v-if="mode === 'menu'">추천 코스에서 가격이 확인된 메뉴 {{ menuSlots.length }}개 중{{ menuSlots.length > slots.length ? ` ${slots.length}개를 올렸어요` : '에서 골라요' }}.</template>
        <template v-else-if="mode === 'restaurant'">가격이 확인된 메뉴가 부족해서, 추천된 식당 {{ slots.length }}곳 중에서 골라요.</template>
        <template v-else>추천된 곳이 한 곳뿐이고 가격이 확인된 메뉴도 부족해 룰렛을 돌릴 수 없어요.</template>
      </p>
    </header>

    <div v-if="mode !== 'none'" class="wheel-wrap">
      <div class="pointer" aria-hidden="true" />
      <svg class="wheel" :class="{ spinning }" viewBox="-130 -130 260 260" role="img"
           :aria-label="`룰렛 칸: ${slots.map((s) => s.menu ?? s.restaurant).join(', ')}`"
           :style="{ transform: `rotate(${angle}deg)`, transitionDuration: `${spinning ? spinMs : 0}ms` }">
        <circle r="126" fill="#fff" stroke="var(--line)" stroke-width="4" />
        <g v-for="(s, i) in slots" :key="i">
          <path :d="slicePath(i)" :fill="COLORS[i % COLORS.length]" stroke="#fff" stroke-width="2" />
          <title>{{ s.menu ?? s.restaurant }}</title>
          <text :transform="labelTransform(i)" text-anchor="middle" dy="4" class="slice-label"
                :class="{ long: (s.menu ?? s.restaurant).length > 6 }">{{ short(s.menu ?? s.restaurant) }}</text>
        </g>
        <circle r="26" fill="var(--accent)" />
        <text text-anchor="middle" dy="6" class="hub">🍚</text>
      </svg>
      <button class="btn primary spin" :disabled="spinning" @click="spin">
        {{ spinning ? '돌아가는 중…' : result ? '다시 돌리기' : '돌려보기' }}
      </button>
    </div>

    <div v-if="result" class="result" aria-live="polite">
      <span class="small muted">{{ result.course + 1 }}번 코스</span>
      <strong class="menu">{{ result.menu ?? result.restaurant }}</strong>
      <span v-if="result.price" class="price">{{ won(result.price) }} <span class="small muted">(확인된 가격)</span></span>
      <span v-if="result.menu" class="where">{{ result.restaurant }}</span>
      <span class="reason small">추천 이유: {{ result.reason }}</span>
      <div class="actions">
        <button class="btn primary" @click="emit('select', result.course)">{{ result.menu ? '이 메뉴로 식당 찾기' : '이 식당 코스 보기' }}</button>
        <button class="btn" @click="emit('locate', result.course)">지도에서 위치 확인</button>
        <button class="btn" :disabled="spinning" @click="spin">{{ result.menu ? '다른 메뉴 뽑기' : '다시 뽑기' }}</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.roulette { border-radius: 24px; padding: 18px; display: grid; gap: 14px; background: linear-gradient(#fffdf8, #fff4e8); }
.roulette.mode-none { background: var(--paper); }
.head h3 { margin: 0; font-family: 'Gowun Dodum', sans-serif; font-size: 20px; }
.head p { margin: 2px 0 0; }
.wheel-wrap { position: relative; display: grid; justify-items: center; gap: 12px; }
.pointer { width: 0; height: 0; border-left: 12px solid transparent; border-right: 12px solid transparent; border-top: 20px solid var(--ink);
  position: absolute; top: -4px; z-index: 2; filter: drop-shadow(0 2px 2px rgba(0,0,0,.2)); }
.wheel { width: min(260px, 70vw); height: auto; transition-property: transform; transition-timing-function: cubic-bezier(.12, .8, .18, 1); }
.slice-label { font-size: 12px; font-weight: 700; fill: var(--ink); }
.slice-label.long { font-size: 10px; }
.hub { font-size: 20px; }
.spin { border-radius: 999px; padding: 10px 26px; font-weight: 700; }
.spin:active:not(:disabled) { transform: scale(.97); }
.result { display: grid; gap: 4px; background: #fff; border: 2px solid var(--accent); border-radius: 18px; padding: 14px; animation: pop .35s ease; }
.menu { font-family: 'Gowun Dodum', sans-serif; font-size: 22px; }
.price { color: var(--accent); font-weight: 700; }
.where { font-weight: 500; }
.reason { color: var(--coffee); }
.actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.actions .btn { border-radius: 999px; }
.btn:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
@keyframes pop { from { opacity: 0; transform: translateY(6px) scale(.98); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .wheel { transition: none !important; } .result { animation: none; } }
</style>
