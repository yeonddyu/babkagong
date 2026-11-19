<script setup lang="ts">
// 추천 지도: 식당(밥그릇 핀)·카페(커피잔 핀) 위치와 선택한 코스의 식당→카페 직선 연결.
// 카카오 지도 키가 있으면 카카오 지도, 없으면 실제 좌표로 그린 위치도(SVG)를 쓴다.
/* eslint-disable @typescript-eslint/no-explicit-any */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Recommendation } from '../types'
import { STATIONS, haversineM, loadKakaoMaps } from '../utils/kakaoMap'

const props = defineProps<{ recommendations: Recommendation[]; selected: number }>()
const emit = defineEmits<{ select: [index: number] }>()

// 같은 위치(소수점 5자리, 약 1m)의 같은 종류 핀은 하나로 묶는다. 위치를 옮겨 그리지 않는다.
interface Pin { kind: 'meal' | 'cafe' | 'station'; courses: number[]; names: string[]; lat: number; lng: number }

const pins = computed<Pin[]>(() => {
  const byKey = new Map<string, Pin>()
  const add = (kind: Pin['kind'], course: number, name: string, lat: number, lng: number) => {
    const key = `${kind}:${lat.toFixed(5)}:${lng.toFixed(5)}`
    const pin = byKey.get(key)
    if (pin) {
      if (course >= 0 && !pin.courses.includes(course)) pin.courses.push(course)
      if (!pin.names.includes(name)) pin.names.push(name)
    } else byKey.set(key, { kind, courses: course >= 0 ? [course] : [], names: [name], lat, lng })
  }
  const areas = new Set<string>()
  props.recommendations.forEach((r, i) => {
    if (r.area) areas.add(r.area)
    if (r.latitude != null && r.longitude != null) add('meal', i, r.name, r.latitude, r.longitude)
    const c = r.cafes[0]
    if (c && c.latitude != null && c.longitude != null) add('cafe', i, c.name, c.latitude, c.longitude)
  })
  areas.forEach((a) => { const s = STATIONS[a]; if (s) add('station', -1, a, s[0], s[1]) })
  return [...byKey.values()]
})
const isOn = (p: Pin) => p.courses.includes(props.selected)
const courseLabel = (p: Pin) => p.courses.map((c) => c + 1).join('·')
function pick(p: Pin) {
  if (!p.courses.length) return
  const next = p.courses.find((c) => c !== props.selected) ?? p.courses[0]!
  emit('select', isOn(p) && p.courses.length > 1 ? next : p.courses.includes(props.selected) ? props.selected : p.courses[0]!)
}

const link = computed(() => {
  const r = props.recommendations[props.selected]
  const c = r?.cafes[0]
  if (!r || !c || r.latitude == null || r.longitude == null || c.latitude == null || c.longitude == null) return null
  return { from: [r.latitude, r.longitude] as [number, number], to: [c.latitude, c.longitude] as [number, number],
           meters: c.distance_m ?? Math.round(haversineM([r.latitude, r.longitude], [c.latitude, c.longitude])), cafe: c.name }
})

// ---------------------------------------------------------------- 카카오 지도
const mapEl = ref<HTMLElement | null>(null)
const mode = ref<'loading' | 'kakao' | 'fallback'>('loading')
let kakao: any = null
let map: any = null
let overlays: any[] = []
let line: any = null

function clearKakao() {
  overlays.forEach((o) => o.setMap(null))
  overlays = []
  if (line) line.setMap(null)
  line = null
}

function pinHtml(p: Pin): HTMLElement {
  const el = document.createElement('button')
  el.type = 'button'
  el.className = `pin ${p.kind}${isOn(p) ? ' on' : ''}`
  el.setAttribute('aria-label', `${p.kind === 'meal' ? '식당' : p.kind === 'cafe' ? '카페' : '역'} ${p.names.join(', ')}`)
  el.title = p.names.join(', ')
  const icon = document.createElement('span')
  icon.textContent = p.kind === 'meal' ? '🍚' : p.kind === 'cafe' ? '☕' : '🚇'
  el.appendChild(icon)
  if (p.kind === 'meal') {
    const num = document.createElement('b')
    num.textContent = courseLabel(p)
    el.appendChild(num)
  }
  if (p.courses.length) el.addEventListener('click', () => pick(p))
  return el
}

function drawKakao() {
  if (!kakao || !map) return
  clearKakao()
  const bounds = new kakao.maps.LatLngBounds()
  for (const p of pins.value) {
    const pos = new kakao.maps.LatLng(p.lat, p.lng)
    bounds.extend(pos)
    const ov = new kakao.maps.CustomOverlay({ position: pos, content: pinHtml(p), yAnchor: 1, zIndex: isOn(p) ? 3 : 1 })
    ov.setMap(map)
    overlays.push(ov)
  }
  if (link.value) {
    line = new kakao.maps.Polyline({
      path: [new kakao.maps.LatLng(...link.value.from), new kakao.maps.LatLng(...link.value.to)],
      strokeWeight: 4, strokeColor: '#d9622b', strokeOpacity: 0.9, strokeStyle: 'shortdash',
    })
    line.setMap(map)
  }
  if (pins.value.length) map.setBounds(bounds, 40, 40, 40, 40)
}

onMounted(async () => {
  kakao = await loadKakaoMaps()
  if (!kakao || !mapEl.value) { mode.value = 'fallback'; return }
  mode.value = 'kakao'
  await nextTick()
  const first = pins.value[0]
  map = new kakao.maps.Map(mapEl.value, { center: new kakao.maps.LatLng(first?.lat ?? 37.4993, first?.lng ?? 127.032), level: 4 })
  drawKakao()
})
onBeforeUnmount(clearKakao)
watch([pins, () => props.selected], () => { if (mode.value === 'kakao') drawKakao() })

// ---------------------------------------------------------------- 좌표 위치도 (키가 없을 때)
const W = 640
const H = 360
const PAD = 36
const projected = computed(() => {
  const ps = pins.value
  if (!ps.length) return { pts: [] as (Pin & { x: number; y: number })[], project: (_: [number, number]) => [0, 0] as [number, number] }
  const lats = ps.map((p) => p.lat)
  const lngs = ps.map((p) => p.lng)
  const kx = Math.cos((lats.reduce((a, b) => a + b, 0) / lats.length) * Math.PI / 180)
  const minX = Math.min(...lngs) * kx, maxX = Math.max(...lngs) * kx
  const minY = Math.min(...lats), maxY = Math.max(...lats)
  const span = Math.max(maxX - minX, maxY - minY, 0.0012)
  const scale = Math.min((W - PAD * 2) / span, (H - PAD * 2) / span)
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2
  const project = ([lat, lng]: [number, number]): [number, number] => [W / 2 + (lng * kx - cx) * scale, H / 2 - (lat - cy) * scale]
  return { pts: ps.map((p) => { const [x, y] = project([p.lat, p.lng]); return { ...p, x, y } }), project }
})
const fallbackLine = computed(() => {
  if (!link.value) return null
  const [x1, y1] = projected.value.project(link.value.from)
  const [x2, y2] = projected.value.project(link.value.to)
  // 라벨은 선의 중점에서 수직 방향으로 비켜 핀을 가리지 않게 둔다
  const len = Math.hypot(x2 - x1, y2 - y1) || 1
  const nx = -(y2 - y1) / len, ny = (x2 - x1) / len
  return { x1, y1, x2, y2, mx: (x1 + x2) / 2 + nx * 26, my: (y1 + y2) / 2 + ny * 26 + 4 }
})
</script>

<template>
  <section class="map-card" aria-label="추천 지도">
    <div v-show="mode === 'kakao'" ref="mapEl" class="kakao-map" />
    <svg v-if="mode !== 'kakao'" class="mini-map" :viewBox="`0 0 ${W} ${H}`" role="img"
         :aria-label="`추천 식당과 카페 위치도, ${recommendations.length}개 코스`">
      <defs>
        <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
          <path d="M 32 0 L 0 0 0 32" fill="none" stroke="var(--line)" stroke-width="1" />
        </pattern>
      </defs>
      <rect :width="W" :height="H" fill="url(#grid)" />
      <g v-if="fallbackLine" class="link">
        <line :x1="fallbackLine.x1" :y1="fallbackLine.y1" :x2="fallbackLine.x2" :y2="fallbackLine.y2" />
        <text :x="fallbackLine.mx" :y="fallbackLine.my" text-anchor="middle">직선 {{ link?.meters }}m</text>
      </g>
      <g v-for="p in projected.pts" :key="p.kind + p.lat + p.lng" class="svg-pin" :class="[p.kind, { on: isOn(p) }]"
         :transform="`translate(${p.x} ${p.y})`" :role="p.courses.length ? 'button' : undefined"
         :aria-label="p.courses.length ? `${courseLabel(p)}번 코스 ${p.kind === 'meal' ? '식당' : '카페'} ${p.names.join(', ')}` : p.names[0]"
         @click="pick(p)">
        <title>{{ p.names.join(', ') }}</title>
        <circle :r="p.kind === 'station' ? 7 : p.kind === 'meal' ? (p.courses.length > 1 ? 19 : 15) : 11" />
        <text v-if="p.kind === 'meal'" text-anchor="middle" dy="5">{{ courseLabel(p) }}</text>
        <text v-else-if="p.kind === 'cafe'" text-anchor="middle" dy="4" class="glyph">☕</text>
        <text v-else text-anchor="middle" dy="-12" class="station-label">{{ p.names[0] }}</text>
      </g>
    </svg>
    <footer class="legend small">
      <span><i class="dot meal" />식당</span>
      <span><i class="dot cafe" />카페</span>
      <span><i class="dash" />식당→카페 직선 (실제 경로 아님)</span>
      <span v-if="mode === 'fallback'" class="muted">카카오 지도 키가 없어 좌표로 그린 위치도예요</span>
      <span v-if="link" class="link-note">선택한 코스: {{ link.cafe }}까지 직선 {{ link.meters }}m</span>
    </footer>
  </section>
</template>

<style scoped>
.map-card { background: var(--paper); border: 1px solid var(--line); border-radius: 26px; overflow: hidden; }
.kakao-map { width: 100%; height: 340px; }
.mini-map { display: block; width: 100%; height: auto; background: #fbf6ec; }
.link line { stroke: var(--accent); stroke-width: 3; stroke-dasharray: 7 6; }
.link text { fill: var(--accent); font-size: 13px; font-weight: 700; paint-order: stroke; stroke: #fbf6ec; stroke-width: 4px; }
.svg-pin { cursor: pointer; transition: transform .25s ease; }
.svg-pin circle { stroke: #fff; stroke-width: 3; }
.svg-pin.meal circle { fill: #f3c7ad; }
.svg-pin.cafe circle { fill: #d9c7b5; }
.svg-pin.station circle { fill: var(--ink); }
.svg-pin.station { cursor: default; }
.svg-pin.meal.on circle { fill: var(--accent); }
.svg-pin.cafe.on circle { fill: var(--coffee); }
.svg-pin text { font-size: 13px; font-weight: 700; fill: var(--ink); pointer-events: none; }
.svg-pin.on text { fill: #fff; }
.svg-pin .glyph { font-size: 11px; }
.svg-pin .station-label { fill: var(--ink); font-size: 12px; font-weight: 500; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: center; padding: 10px 16px; border-top: 1px solid var(--line); }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
.dot.meal { background: var(--accent); }
.dot.cafe { background: var(--coffee); }
.dash { width: 22px; border-top: 3px dashed var(--accent); display: inline-block; }
.link-note { margin-left: auto; font-weight: 500; color: var(--accent); }
:deep(.pin) { display: inline-flex; align-items: center; gap: 2px; padding: 4px 8px; border-radius: 999px; border: 2px solid #fff;
  background: #fff3ea; box-shadow: 0 3px 10px rgba(91, 70, 54, .25); font-size: 13px; transform: translateY(-4px); transition: transform .2s; }
:deep(.pin.cafe) { background: #f1e7dd; }
:deep(.pin.station) { background: var(--ink); color: #fff; }
:deep(.pin.on) { background: var(--accent); color: #fff; transform: translateY(-8px) scale(1.12); }
:deep(.pin.cafe.on) { background: var(--coffee); }
@media (prefers-reduced-motion: reduce) { .svg-pin, :deep(.pin) { transition: none; } }
</style>
