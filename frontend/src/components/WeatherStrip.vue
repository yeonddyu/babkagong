<script setup lang="ts">
// 기상청 단기예보 결과를 보여 주는 날씨 띠. 응답이 없으면 아무것도 꾸미지 않는다.
// 분위기 판정 기준은 백엔드 정책(backend/app/agent/policy.py)과 같은 값을 쓴다.
import { computed } from 'vue'
import { weatherMood } from '../utils/weather'

const props = defineProps<{ weather: Record<string, any> | null; policy: string[] }>()
const mood = computed(() => weatherMood(props.weather))

const ICON: Record<string, string> = { rain: '🌧', snow: '🌨', cold: '🧣', hot: '☀️', clear: '🌤', cloudy: '☁️' }
const TITLE: Record<string, string> = {
  rain: '비 소식이 있어요', snow: '눈 소식이 있어요', cold: '쌀쌀한 날이에요', hot: '더운 날이에요', clear: '맑은 날이에요', cloudy: '구름 낀 날이에요',
}
const when = computed(() => {
  const t = props.weather?.forecast_datetime as string | undefined
  return t ? `${t.slice(5, 10).replace('-', '/')} ${t.slice(11, 16)} 예보` : ''
})
</script>

<template>
  <section v-if="weather && mood" class="weather card" :class="`mood-${mood}`" aria-label="방문 시각 날씨">
    <div v-if="mood === 'rain' || mood === 'snow'" class="fx" aria-hidden="true">
      <i v-for="n in 12" :key="n" :style="{ '--n': n }" />
    </div>
    <span class="icon" aria-hidden="true">{{ ICON[mood] }}</span>
    <div class="main">
      <strong>{{ TITLE[mood] }}</strong>
      <span class="small">
        {{ weather.temperature_c ?? '기온 미확인' }}<template v-if="weather.temperature_c != null">°C</template>
        · 강수확률 {{ weather.precipitation_probability ?? '미확인' }}<template v-if="weather.precipitation_probability != null">%</template>
        · {{ weather.precipitation_type ?? '강수형태 미확인' }}
      </span>
    </div>
    <div class="meta small">
      <span>{{ when }} · 기상청 단기예보</span>
      <span v-for="p in policy" :key="p" class="policy">{{ p }}</span>
    </div>
  </section>
</template>

<style scoped>
.weather { position: relative; overflow: hidden; display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px;
  border-radius: 22px; padding: 14px 18px; --tint: #fff6ea; background: var(--tint); }
.mood-rain { --tint: #e9eef3; border-color: #c9d5df; }
.mood-snow { --tint: #eef3f7; border-color: #d4dee6; }
.mood-cold { --tint: #eef1f4; border-color: #d3dbe2; }
.mood-hot { --tint: #ffefd9; border-color: #f4c98f; }
.mood-clear { --tint: #fff6e3; border-color: #f1dcb0; }
.mood-cloudy { --tint: #f3efe9; }
.icon { font-size: 30px; position: relative; z-index: 1; }
.main { display: flex; flex-direction: column; position: relative; z-index: 1; }
.main strong { font-family: 'Gowun Dodum', sans-serif; font-size: 18px; }
.meta { margin-left: auto; display: flex; flex-direction: column; align-items: flex-end; gap: 2px; color: var(--muted); position: relative; z-index: 1; }
.policy { color: var(--coffee); }
.fx { position: absolute; inset: 0; pointer-events: none; }
.fx i { position: absolute; top: -12px; left: calc(var(--n) * 8%); width: 2px; height: 10px; border-radius: 2px;
  background: #8fa7bb; opacity: .55; animation: fall 1.4s linear infinite; animation-delay: calc(var(--n) * -0.13s); }
.mood-snow .fx i { width: 6px; height: 6px; border-radius: 50%; background: #fff; opacity: .9; animation-duration: 3.2s; }
@keyframes fall { to { transform: translateY(110px); } }
@media (prefers-reduced-motion: reduce) { .fx { display: none; } }
@media (max-width: 600px) { .meta { margin-left: 0; align-items: flex-start; } }
</style>
