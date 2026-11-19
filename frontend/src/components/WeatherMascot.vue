<script setup lang="ts">
// 날씨 반응형 마스코트 '밥알이' (직접 그린 SVG). 새 API 호출 없이 응답의 기상청 예보(weather)만 쓴다.
// 예보값임을 항상 표시하고, 강수형태(비 예보)와 강수확률(비 올 수도)을 구분한다.
import { computed } from 'vue'
import { mascotLine, mascotState } from '../utils/weather'

const props = defineProps<{ weather: Record<string, any> | null | undefined; hasResult: boolean }>()
const state = computed(() => mascotState(props.weather, props.hasResult))
const line = computed(() => mascotLine(state.value, props.weather))
const w = computed(() => props.weather ?? null)
const when = computed(() => {
  const t = w.value?.forecast_datetime as string | undefined
  return t ? `${t.slice(5, 10).replace('-', '/')} ${t.slice(11, 16)}` : null
})
const facts = computed(() => {
  if (!w.value || state.value === 'neutral') return null
  const v = w.value
  return [
    v.temperature_c != null ? `${v.temperature_c}°C` : '기온 미확인',
    v.precipitation_probability != null ? `강수확률 ${v.precipitation_probability}%` : '강수확률 미확인',
    v.precipitation_type ? `강수형태 ${v.precipitation_type}` : '강수형태 미확인',
  ]
})
const LABEL: Record<string, string> = {
  idle: '기다리는 중', neutral: '날씨 미확인', rain: '비 예보', 'rain-maybe': '비 올 수도', snow: '눈 예보',
  cold: '쌀쌀함', hot: '더움', clear: '맑음', mild: '무난함',
}
</script>

<template>
  <section class="mascot card" :class="`st-${state}`" :data-state="state" aria-label="날씨 마스코트">
    <svg class="char" viewBox="0 0 120 120" role="img" :aria-label="`밥알이: ${LABEL[state]}`">
      <!-- 해 (맑음·더움) -->
      <g v-if="state === 'clear' || state === 'hot'" class="sun">
        <circle cx="98" cy="20" r="10" fill="#f6b73c" />
        <g stroke="#f6b73c" stroke-width="3" stroke-linecap="round">
          <line x1="98" y1="3" x2="98" y2="7" /><line x1="98" y1="33" x2="98" y2="37" />
          <line x1="81" y1="20" x2="85" y2="20" /><line x1="111" y1="20" x2="115" y2="20" />
        </g>
      </g>
      <!-- 구름 (비 올 수도·무난함·비·눈) -->
      <g v-if="['rain', 'rain-maybe', 'mild', 'snow'].includes(state)" class="cloud">
        <ellipse cx="86" cy="18" rx="20" ry="10" fill="#c9d2da" />
        <ellipse cx="74" cy="20" rx="12" ry="8" fill="#d8dfe5" />
      </g>
      <!-- 빗방울 / 눈송이 -->
      <g v-if="state === 'rain'" class="drops" fill="#6f95b4">
        <path v-for="(x, i) in [12, 30, 100, 110]" :key="i" :d="`M${x} 34 q3 6 0 8 q-3 -2 0 -8z`" :style="{ '--d': `${i * 0.25}s` }" />
      </g>
      <g v-if="state === 'rain-maybe'" class="drops maybe" fill="#9ab3c7">
        <path d="M84 32 q3 6 0 8 q-3 -2 0 -8z" style="--d: 0s" />
      </g>
      <g v-if="state === 'snow'" class="flakes" fill="#fff" stroke="#b9c7d3">
        <circle v-for="(x, i) in [14, 32, 98, 110]" :key="i" :cx="x" cy="36" r="3" :style="{ '--d': `${i * 0.4}s` }" />
      </g>
      <!-- 김 (쌀쌀함: 따뜻한 국물) -->
      <g v-if="state === 'cold'" class="steam" fill="none" stroke="#c9b8a6" stroke-width="3" stroke-linecap="round">
        <path d="M48 16 q-5 -6 0 -12" /><path d="M60 14 q-5 -6 0 -12" style="--d: .3s" /><path d="M72 16 q-5 -6 0 -12" style="--d: .6s" />
      </g>

      <!-- 몸: 밥이 담긴 그릇 -->
      <g class="body">
        <path d="M30 52 q30 -34 60 0 z" fill="#fffdf7" stroke="#e5d9c6" stroke-width="2" />
        <circle cx="46" cy="44" r="2" fill="#efe6d6" /><circle cx="70" cy="40" r="2" fill="#efe6d6" /><circle cx="58" cy="36" r="2" fill="#efe6d6" />
        <path d="M24 52 h72 q-4 34 -36 36 q-32 -2 -36 -36 z" :fill="state === 'neutral' || state === 'idle' ? '#d9cfc2' : '#e98a5a'" />
        <path d="M44 88 h32 l-4 8 h-24 z" fill="#c7643c" />
        <!-- 얼굴 -->
        <template v-if="state === 'hot'">
          <rect x="38" y="58" width="18" height="9" rx="4" fill="#2c2420" /><rect x="64" y="58" width="18" height="9" rx="4" fill="#2c2420" />
          <line x1="56" y1="61" x2="64" y2="61" stroke="#2c2420" stroke-width="2" />
        </template>
        <template v-else-if="state === 'neutral'">
          <line x1="44" y1="63" x2="52" y2="63" stroke="#2c2420" stroke-width="3" stroke-linecap="round" />
          <line x1="68" y1="63" x2="76" y2="63" stroke="#2c2420" stroke-width="3" stroke-linecap="round" />
        </template>
        <template v-else>
          <circle cx="48" cy="63" r="3.5" fill="#2c2420" /><circle cx="72" cy="63" r="3.5" fill="#2c2420" />
        </template>
        <circle cx="40" cy="70" r="4" fill="#f6b8a0" opacity=".8" /><circle cx="80" cy="70" r="4" fill="#f6b8a0" opacity=".8" />
        <path v-if="state === 'neutral'" d="M54 74 h12" stroke="#2c2420" stroke-width="2.5" stroke-linecap="round" />
        <path v-else-if="state === 'rain-maybe' || state === 'snow'" d="M55 75 q5 -3 10 0" fill="none" stroke="#2c2420" stroke-width="2.5" stroke-linecap="round" />
        <path v-else d="M54 72 q6 6 12 0" fill="none" stroke="#2c2420" stroke-width="2.5" stroke-linecap="round" />
      </g>

      <!-- 목도리 (쌀쌀함·눈) -->
      <g v-if="state === 'cold' || state === 'snow'" class="scarf">
        <path d="M27 78 q33 12 66 0 v7 q-33 12 -66 0 z" fill="#5f8fb8" />
        <rect x="76" y="82" width="8" height="16" rx="2" fill="#4c7aa2" />
      </g>
      <!-- 우산 (비) / 접은 우산 (비 올 수도) -->
      <g v-if="state === 'rain'" class="umbrella">
        <path d="M2 50 q20 -26 40 0 q-5 -4 -10 0 q-5 -4 -10 0 q-5 -4 -10 0 q-5 -4 -10 0 z" fill="#7aa5c7" />
        <path d="M22 48 v34 q0 5 5 5" fill="none" stroke="#2c2420" stroke-width="2.5" stroke-linecap="round" />
      </g>
      <g v-if="state === 'rain-maybe'" class="umbrella-closed">
        <path d="M100 58 l6 30 l-6 2 z" fill="#7aa5c7" /><path d="M103 89 q0 5 -5 5" fill="none" stroke="#2c2420" stroke-width="2.5" stroke-linecap="round" />
      </g>
      <!-- 부채 (더움) -->
      <g v-if="state === 'hot'" class="fan">
        <path d="M98 70 l16 -14 q4 10 -4 20 z" fill="#f4c98f" stroke="#e0a560" stroke-width="1.5" />
        <line x1="98" y1="70" x2="92" y2="80" stroke="#c7643c" stroke-width="3" stroke-linecap="round" />
      </g>
      <!-- 물음표 (날씨 미확인) -->
      <text v-if="state === 'neutral'" x="96" y="40" class="q">?</text>
    </svg>

    <div class="talk">
      <p class="bubble" aria-live="polite">{{ line }}</p>
      <p v-if="facts" class="facts small">
        <span class="tag">{{ when ? `${when} 예보` : '예보' }}</span>
        {{ facts.join(' · ') }}
      </p>
      <p v-if="state === 'rain-maybe'" class="small muted">강수확률만 높고 강수형태는 ‘없음’인 예보예요 (실제 비가 온다는 뜻은 아니에요).</p>
      <p v-if="facts" class="small muted source">기상청 단기예보 기준 · 실측값 아님</p>
    </div>
  </section>
</template>

<style scoped>
.mascot { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-radius: 22px; --tint: #fffaf2; background: var(--tint); }
.st-rain, .st-rain-maybe { --tint: #eef2f6; }
.st-snow, .st-cold { --tint: #f0f3f6; }
.st-hot { --tint: #fff0dc; }
.st-clear { --tint: #fff7e4; }
.st-neutral { --tint: #f5f2ee; }
.char { width: 96px; height: 96px; flex: none; overflow: visible; }
.body { transform-origin: 60px 96px; animation: bob 2.8s ease-in-out infinite; }
.st-cold .body { animation: shiver .5s ease-in-out infinite; }
.st-neutral .body, .st-idle .body { animation-duration: 4s; }
.drops path, .flakes circle { animation: drop 1.2s linear infinite; animation-delay: var(--d); }
.flakes circle { animation-duration: 2.4s; }
.drops.maybe path { animation-duration: 2.6s; }
.steam path { animation: steam 1.8s ease-in-out infinite; animation-delay: var(--d, 0s); }
.fan { transform-origin: 98px 70px; animation: fan .6s ease-in-out infinite alternate; }
.sun { transform-origin: 98px 20px; animation: spinSun 12s linear infinite; }
.q { font: 700 22px 'Gowun Dodum', sans-serif; fill: var(--muted); }
.talk { display: grid; gap: 4px; min-width: 0; }
.bubble { position: relative; margin: 0; background: #fff; border: 1px solid var(--line); border-radius: 16px; padding: 8px 12px;
  font-family: 'Gowun Dodum', sans-serif; font-size: 16px; }
.bubble::before { content: ''; position: absolute; left: -7px; top: 14px; width: 12px; height: 12px; background: #fff;
  border-left: 1px solid var(--line); border-bottom: 1px solid var(--line); transform: rotate(45deg); }
.facts { margin: 0; }
.tag { display: inline-block; background: var(--ink); color: #fff; border-radius: 999px; padding: 1px 8px; margin-right: 4px; font-size: 11px; }
.source { margin: 0; }
.talk p.muted { margin: 0; }
@keyframes bob { 50% { transform: translateY(-3px); } }
@keyframes shiver { 25% { transform: translateX(-1px); } 75% { transform: translateX(1px); } }
@keyframes drop { from { transform: translateY(0); opacity: 1; } to { transform: translateY(26px); opacity: 0; } }
@keyframes steam { 0%, 100% { opacity: .2; transform: translateY(2px); } 50% { opacity: 1; transform: translateY(-2px); } }
@keyframes fan { to { transform: rotate(-18deg); } }
@keyframes spinSun { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .body, .drops path, .flakes circle, .steam path, .fan, .sun { animation: none !important; }
}
</style>
