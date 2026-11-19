<script setup lang="ts">
// 메뉴 룰렛: 이번 추천 후보에서 가격이 확인된 메뉴만 돌린다. 결과는 출처 식당(코스)과 함께 보여 준다.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { Recommendation } from '../types'

const props = withDefaults(defineProps<{ recommendations: Recommendation[]; random?: () => number; spinMs?: number }>(), {
  random: () => Math.random(),
  spinMs: 1600,
})
const emit = defineEmits<{ select: [index: number] }>()

interface Slot { menu: string; price: number; course: number; restaurant: string }
const slots = computed<Slot[]>(() =>
  props.recommendations.flatMap((r, i) =>
    r.matched_menus.filter((m) => m.price_krw).map((m) => ({ menu: m.name, price: m.price_krw!, course: i, restaurant: r.name }))))

const shown = ref<Slot | null>(null)
const result = ref<Slot | null>(null)
const spinning = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null
watch(slots, () => { shown.value = null; result.value = null })
onBeforeUnmount(() => { if (timer) clearTimeout(timer) })

function reducedMotion() {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function spin() {
  if (spinning.value || slots.value.length < 2) return
  const pick = slots.value[Math.min(slots.value.length - 1, Math.floor(props.random() * slots.value.length))]!
  result.value = null
  if (props.spinMs <= 0 || reducedMotion()) {
    shown.value = pick
    result.value = pick
    return
  }
  spinning.value = true
  const start = Date.now()
  let k = 0
  const tick = () => {
    const t = (Date.now() - start) / props.spinMs
    if (t >= 1) {
      shown.value = pick
      result.value = pick
      spinning.value = false
      return
    }
    shown.value = slots.value[k++ % slots.value.length]!
    timer = setTimeout(tick, 50 + 220 * t * t) // 점점 느려짐
  }
  tick()
}

const won = (v: number) => `${v.toLocaleString()}원`
</script>

<template>
  <section v-if="slots.length >= 2" class="roulette card" aria-label="메뉴 룰렛">
    <div class="head">
      <div>
        <h3>못 고르겠다면, 메뉴 룰렛</h3>
        <p class="muted small">추천 코스에서 가격이 확인된 메뉴 {{ slots.length }}개 중에서 골라요.</p>
      </div>
      <button class="btn primary spin" :disabled="spinning" @click="spin">{{ spinning ? '돌리는 중…' : result ? '다시 돌리기' : '룰렛 돌리기' }}</button>
    </div>
    <div class="window" :class="{ spinning, done: !!result }" aria-live="polite">
      <template v-if="shown">
        <span class="bowl" aria-hidden="true">🍚</span>
        <strong class="menu">{{ shown.menu }}</strong>
        <span class="price">{{ won(shown.price) }}</span>
        <span class="from small muted">{{ shown.course + 1 }}번 코스 · {{ shown.restaurant }}</span>
      </template>
      <span v-else class="muted small">버튼을 누르면 메뉴가 돌아가요</span>
    </div>
    <button v-if="result" class="btn go" @click="emit('select', result.course)">{{ result.course + 1 }}번 코스 보기</button>
  </section>
</template>

<style scoped>
.roulette { border-radius: 22px; padding: 16px 18px; display: grid; gap: 12px; background: linear-gradient(#fffdf8, #fff6ec); }
.head { display: flex; gap: 12px; align-items: flex-start; justify-content: space-between; }
h3 { margin: 0; font-family: 'Gowun Dodum', sans-serif; font-size: 17px; }
.head p { margin: 2px 0 0; }
.spin { border-radius: 999px; flex: none; }
.window { min-height: 64px; border-radius: 18px; border: 2px dashed var(--line); background: #fff; display: flex; flex-wrap: wrap;
  align-items: center; gap: 4px 10px; padding: 10px 14px; }
.window.spinning { border-color: var(--accent); }
.window.done { border-style: solid; border-color: var(--accent); animation: pop .3s ease; }
.bowl { font-size: 22px; }
.menu { font-size: 18px; }
.price { color: var(--accent); font-weight: 700; }
.from { flex-basis: 100%; }
.go { justify-self: start; border-radius: 999px; }
@keyframes pop { 50% { transform: scale(1.03); } }
@media (prefers-reduced-motion: reduce) { .window.done { animation: none; } }
</style>
