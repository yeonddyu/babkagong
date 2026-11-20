<script setup lang="ts">
// 인터랙티브 밥→카공 지도.
// - 식당(오렌지 밥그릇 핀)·카페(브라운 커피잔 핀)·역 핀, 선택한 코스는 강조하고 고른 카페까지 점선 직선으로 잇는다.
// - 선택한 코스의 다른 카페 후보도 작은 핀으로 보여 주고, 핀을 누르면 장소 정보 카드를 연다.
// - 카카오 지도 키가 없거나 불러오지 못하면 실제 좌표로 그린 위치도 + 장소 목록으로 대신한다.
// 연결선은 실제 도보 경로가 아니다. 확인되지 않은 정보는 '확인 필요'·'정보 없음'으로만 표시한다.
/* eslint-disable @typescript-eslint/no-explicit-any */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Focus } from '../stores/course'
import type { Cafe, Origin, Recommendation } from '../types'
import { STATIONS, haversineM, kakaoMapKey, loadKakaoMaps } from '../utils/kakaoMap'

const props = withDefaults(defineProps<{
  recommendations: Recommendation[]
  selected: number
  cafeChoice?: Record<number, number>
  focus?: Focus | null
  interactive?: boolean // 저장한 계획처럼 보기만 할 때는 false
  origin?: Origin | null // 거리 기준점 (출구면 핀으로 표시)
}>(), { cafeChoice: () => ({}), focus: null, interactive: true, origin: null })
const emit = defineEmits<{ select: [index: number]; focus: [f: Focus | null]; chooseCafe: [course: number, cafe: number] }>()

const cafeIdx = (course: number) => props.cafeChoice[course] ?? 0
const cafeOf = (course: number): Cafe | undefined => {
  const r = props.recommendations[course]
  return r?.cafes[cafeIdx(course)] ?? r?.cafes[0]
}

// 같은 위치(소수점 5자리, 약 1m)의 같은 종류 핀은 하나로 묶는다. 위치를 옮겨 그리지 않는다.
interface Ref { course: number; cafe: number }
interface Pin { kind: 'meal' | 'cafe' | 'alt' | 'station' | 'exit'; courses: number[]; refs: Ref[]; names: string[]; lat: number; lng: number }

const pins = computed<Pin[]>(() => {
  const byKey = new Map<string, Pin>()
  const add = (kind: Pin['kind'], ref: Ref | null, name: string, lat: number, lng: number) => {
    const key = `${kind === 'alt' ? 'cafe' : kind}:${lat.toFixed(5)}:${lng.toFixed(5)}`
    const pin = byKey.get(key)
    if (pin) {
      if (ref && !pin.courses.includes(ref.course)) pin.courses.push(ref.course)
      if (ref) pin.refs.push(ref)
      if (!pin.names.includes(name)) pin.names.push(name)
      if (pin.kind === 'alt' && kind === 'cafe') pin.kind = 'cafe'
    } else byKey.set(key, { kind, courses: ref ? [ref.course] : [], refs: ref ? [ref] : [], names: [name], lat, lng })
  }
  const areas = new Set<string>()
  props.recommendations.forEach((r, i) => {
    if (r.area) areas.add(r.area)
    if (r.latitude != null && r.longitude != null) add('meal', { course: i, cafe: -1 }, r.name, r.latitude, r.longitude)
    r.cafes.forEach((c, ci) => {
      if (c.latitude == null || c.longitude == null) return
      const chosen = ci === cafeIdx(i) || (!r.cafes[cafeIdx(i)] && ci === 0)
      if (chosen) add('cafe', { course: i, cafe: ci }, c.name, c.latitude, c.longitude)
      else if (i === props.selected && props.interactive) add('alt', { course: i, cafe: ci }, c.name, c.latitude, c.longitude)
    })
  })
  // 역 표시: 응답의 거리 기준점(역 중심)을 쓰고, 없으면(저장한 계획 등) 알고 있는 역 좌표만 표시
  if (props.origin?.kind === 'station') add('station', null, props.origin.label, props.origin.latitude, props.origin.longitude)
  else areas.forEach((a) => { const s = STATIONS[a]; if (s) add('station', null, a, s[0], s[1]) })
  // 사용자가 말한 출구를 거리 기준점으로 썼다면 출구 위치도 표시
  if (props.origin?.kind === 'exit') add('exit', null, props.origin.label, props.origin.latitude, props.origin.longitude)
  const order = { station: 0, exit: 1, alt: 2, meal: 3, cafe: 4 }
  return [...byKey.values()].sort((a, b) => order[a.kind] - order[b.kind])
})
const isOn = (p: Pin) => p.courses.includes(props.selected)
const isFocused = (p: Pin) => !!props.focus && p.refs.some((r) =>
  r.course === props.focus!.course && (props.focus!.kind === 'meal' ? r.cafe === -1 : r.cafe === props.focus!.cafe))
const courseLabel = (p: Pin) => p.courses.map((c) => c + 1).join('·')

function pick(p: Pin) {
  if (!p.refs.length || !props.interactive) return
  // 겹친 핀은 누를 때마다 다른 코스로 넘어간다
  const refs = p.refs
  const cur = refs.findIndex((r) => r.course === props.selected)
  const ref = isOn(p) && refs.length > 1 ? refs[(cur + 1) % refs.length]! : refs[Math.max(cur, 0)]!
  emit('select', ref.course)
  emit('focus', ref.cafe === -1 ? { kind: 'meal', course: ref.course, cafe: cafeIdx(ref.course) }
    : { kind: 'cafe', course: ref.course, cafe: ref.cafe })
}

const link = computed(() => {
  const r = props.recommendations[props.selected]
  const c = cafeOf(props.selected)
  if (!r || !c || r.latitude == null || r.longitude == null || c.latitude == null || c.longitude == null) return null
  return { from: [r.latitude, r.longitude] as [number, number], to: [c.latitude, c.longitude] as [number, number],
           meters: c.distance_m ?? Math.round(haversineM([r.latitude, r.longitude], [c.latitude, c.longitude])), cafe: c.name }
})

// ---------------------------------------------------------------- 장소 정보 카드
const card = computed(() => {
  const f = props.focus
  if (!f) return null
  const r = props.recommendations[f.course]
  if (!r) return null
  if (f.kind === 'meal') {
    const menus = r.matched_menus.length ? r.matched_menus : r.sample_menus ?? []
    const reasons = r.checks.filter((c) => c.result === 'pass').map((c) => `${c.criterion} 충족`)
    if (r.distance_m != null) reasons.unshift(`${r.distance_from ?? '역'}에서 직선 ${r.distance_m}m`)
    return { kind: 'meal' as const, course: f.course, title: r.name, address: r.address ?? '정보 없음', menus,
             hours: r.business_hours ?? '확인 필요', reasons, search: `https://map.kakao.com/link/search/${encodeURIComponent(r.name)}` }
  }
  const c = r.cafes[f.cafe]
  if (!c) return null
  return { kind: 'cafe' as const, course: f.course, cafeIndex: f.cafe, title: c.name, address: c.road_address ?? c.address ?? '정보 없음',
           url: c.place_url, distance: c.distance_m, chosen: cafeIdx(f.course) === f.cafe, restaurant: r.name }
})
const won = (v: number | null) => (v ? `${v.toLocaleString()}원` : '가격 정보 없음')

// ---------------------------------------------------------------- 카카오 지도
const mapEl = ref<HTMLElement | null>(null)
const mode = ref<'loading' | 'kakao' | 'fallback'>('loading')
const fallbackReason = kakaoMapKey()
  ? '카카오 지도를 불러오지 못해 좌표로 그린 위치도예요 (카카오 앱의 Web 도메인 등록을 확인해 주세요)'
  : '카카오 지도 키가 없어 좌표로 그린 위치도예요'
let kakao: any = null
let map: any = null
let overlays: any[] = []
let line: any = null
let resizeObs: ResizeObserver | null = null
let lastSize = ''

function clearKakao() {
  overlays.forEach((o) => o.setMap(null))
  overlays = []
  if (line) line.setMap(null)
  line = null
}

function pinHtml(p: Pin): HTMLElement {
  const el = document.createElement('button')
  el.type = 'button'
  el.className = `pin ${p.kind}${isOn(p) ? ' on' : ''}${isFocused(p) ? ' focused' : ''}`
  const label = p.kind === 'meal' ? '식당' : p.kind === 'station' ? '역' : p.kind === 'exit' ? '기준 출구' : '카페'
  el.setAttribute('aria-label', `${label} ${p.names.join(', ')}`)
  el.title = p.names.join(', ')
  const icon = document.createElement('span')
  icon.textContent = p.kind === 'meal' ? '🍚' : p.kind === 'station' ? '🚇' : p.kind === 'exit' ? '🚪' : '☕'
  el.appendChild(icon)
  if (p.kind === 'meal') {
    const num = document.createElement('b')
    num.textContent = courseLabel(p)
    el.appendChild(num)
  }
  if (p.refs.length) el.addEventListener('click', () => pick(p))
  return el
}

function fit(onlySelected: boolean) {
  if (!kakao || !map) return
  const bounds = new kakao.maps.LatLngBounds()
  const pts = onlySelected && link.value ? [link.value.from, link.value.to] : pins.value.map((p) => [p.lat, p.lng] as [number, number])
  pts.forEach(([la, ln]) => bounds.extend(new kakao.maps.LatLng(la, ln)))
  if (pts.length) map.setBounds(bounds, 60, 60, 60, 60)
}

function drawKakao() {
  if (!kakao || !map) return
  clearKakao()
  for (const p of pins.value) {
    const pos = new kakao.maps.LatLng(p.lat, p.lng)
    const ov = new kakao.maps.CustomOverlay({ position: pos, content: pinHtml(p), yAnchor: 1, zIndex: isFocused(p) ? 5 : isOn(p) ? 3 : 1 })
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
}

onMounted(async () => {
  kakao = await loadKakaoMaps()
  if (!kakao || !mapEl.value) { mode.value = 'fallback'; return }
  mode.value = 'kakao'
  await nextTick()
  const first = pins.value[0]
  map = new kakao.maps.Map(mapEl.value, { center: new kakao.maps.LatLng(first?.lat ?? 37.4993, first?.lng ?? 127.032), level: 4 })
  drawKakao()
  fit(false)
  // 숨겨진 탭(모바일)에서 만들어졌거나 창 크기가 바뀌면 지도 크기를 다시 계산하고 범위를 맞춘다
  if (typeof ResizeObserver !== 'undefined') {
    resizeObs = new ResizeObserver(([entry]) => {
      const { width, height } = entry!.contentRect
      const size = `${Math.round(width)}x${Math.round(height)}`
      if (!width || !height || size === lastSize) return
      lastSize = size
      map.relayout()
      drawKakao()
      fit(props.focus != null) // 장소를 보러 온 경우(모바일 지도 탭 전환)는 그 코스로 맞춘다
    })
    resizeObs.observe(mapEl.value)
  }
})
onBeforeUnmount(() => { clearKakao(); resizeObs?.disconnect() })
// 새 추천이면 전체가 보이게, 코스·카페를 바꾸면 그 코스가 보이게
watch(() => props.recommendations, () => { if (mode.value === 'kakao') { drawKakao(); fit(false) } })
watch([() => props.selected, () => props.cafeChoice], () => { if (mode.value === 'kakao') { drawKakao(); fit(true) } }, { deep: true })
watch(() => props.focus, () => { if (mode.value === 'kakao') drawKakao() }, { deep: true })

// ---------------------------------------------------------------- 좌표 위치도 (키가 없을 때)
const W = 640
const H = 360
const PAD = 36
const projected = computed(() => {
  const ps = pins.value
  if (!ps.length) return { pts: [] as (Pin & { x: number; y: number; attached: boolean })[], project: (_: [number, number]) => [0, 0] as [number, number] }
  const lats = ps.map((p) => p.lat)
  const lngs = ps.map((p) => p.lng)
  const kx = Math.cos((lats.reduce((a, b) => a + b, 0) / lats.length) * Math.PI / 180)
  const minX = Math.min(...lngs) * kx, maxX = Math.max(...lngs) * kx
  const minY = Math.min(...lats), maxY = Math.max(...lats)
  const span = Math.max(maxX - minX, maxY - minY, 0.0012)
  const scale = Math.min((W - PAD * 2) / span, (H - PAD * 2) / span)
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2
  const project = ([lat, lng]: [number, number]): [number, number] => [W / 2 + (lng * kx - cx) * scale, H / 2 - (lat - cy) * scale]
  const pts = ps.map((p) => { const [x, y] = project([p.lat, p.lng]); return { ...p, x, y, attached: false } })
  // 식당 핀과 화면상 거의 겹치는 카페 핀은 식당 핀 오른쪽 위에 붙은 배지로 그린다 (같은 위치임을 표시)
  for (const c of pts.filter((p) => p.kind === 'cafe' || p.kind === 'alt')) {
    const m = pts.find((p) => p.kind === 'meal' && Math.hypot(p.x - c.x, p.y - c.y) < 20)
    if (m) { c.x = m.x + 16; c.y = m.y - 16; c.attached = true }
  }
  return { pts, project }
})
const fallbackLine = computed(() => {
  if (!link.value) return null
  const [x1, y1] = projected.value.project(link.value.from)
  const [x2, y2] = projected.value.project(link.value.to)
  const len = Math.hypot(x2 - x1, y2 - y1)
  const clampX = (x: number) => Math.min(W - 60, Math.max(60, x))
  const clampY = (y: number) => Math.min(H - 12, Math.max(18, y))
  if (len < 24) return { short: true, x1, y1, x2, y2, mx: clampX(x1), my: clampY(y1 + 34) }
  const nx = -(y2 - y1) / len, ny = (x2 - x1) / len
  return { short: false, x1, y1, x2, y2, mx: clampX((x1 + x2) / 2 + nx * 26), my: clampY((y1 + y2) / 2 + ny * 26 + 4) }
})
</script>

<template>
  <section class="map-card" aria-label="추천 지도">
    <div class="stage">
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
          <line v-if="!fallbackLine.short" :x1="fallbackLine.x1" :y1="fallbackLine.y1" :x2="fallbackLine.x2" :y2="fallbackLine.y2" />
          <text :x="fallbackLine.mx" :y="fallbackLine.my" text-anchor="middle">{{ fallbackLine.short ? `같은 위치 · 직선 ${link?.meters}m` : `직선 ${link?.meters}m` }}</text>
        </g>
        <g v-for="p in projected.pts" :key="p.kind + p.lat + p.lng" class="svg-pin"
           :class="[p.kind, { on: isOn(p), attached: p.attached, focused: isFocused(p) }]"
           :transform="`translate(${p.x} ${p.y})`" :role="p.refs.length ? 'button' : undefined"
           :tabindex="p.refs.length && interactive ? 0 : undefined"
           :aria-label="p.refs.length ? `${courseLabel(p)}번 코스 ${p.kind === 'meal' ? '식당' : '카페'} ${p.names.join(', ')}` : p.names[0]"
           @click="pick(p)" @keydown.enter.prevent="pick(p)">
          <title>{{ p.names.join(', ') }}</title>
          <circle :r="p.kind === 'station' || p.kind === 'exit' ? 7 : p.kind === 'meal' ? (p.courses.length > 1 ? 19 : 15) : p.kind === 'alt' ? 8 : p.attached ? 9 : 11" />
          <text v-if="p.kind === 'meal'" text-anchor="middle" dy="5">{{ courseLabel(p) }}</text>
          <text v-else-if="p.kind === 'cafe'" text-anchor="middle" dy="4" class="glyph">☕</text>
          <text v-else-if="p.kind === 'station' || p.kind === 'exit'" text-anchor="middle" dy="-12" class="station-label">{{ p.names[0] }}</text>
        </g>
      </svg>

      <aside v-if="card" class="place-card" :class="card.kind" role="dialog" :aria-label="`${card.title} 정보`">
        <button class="close" aria-label="장소 정보 닫기" @click="emit('focus', null)">×</button>
        <span class="kind small">{{ card.course + 1 }}번 코스 · {{ card.kind === 'meal' ? '식당' : '카페' }}</span>
        <h4>{{ card.title }}</h4>
        <p class="small muted">{{ card.address }}</p>
        <template v-if="card.kind === 'meal'">
          <dl class="small">
            <dt>메뉴</dt>
            <dd>
              <template v-if="card.menus.length">
                <span v-for="m in card.menus.slice(0, 3)" :key="m.name" class="m">{{ m.name }} <b>{{ won(m.price_krw) }}</b></span>
              </template>
              <span v-else class="unknown">메뉴 정보 없음</span>
            </dd>
            <dt>영업</dt><dd :class="{ unknown: card.hours === '확인 필요' }">{{ card.hours }}</dd>
            <dt>추천 이유</dt><dd>{{ card.reasons.join(' · ') || '정보 없음' }}</dd>
          </dl>
          <a class="small" :href="card.search" target="_blank" rel="noopener">카카오맵에서 검색</a>
        </template>
        <template v-else>
          <dl class="small">
            <dt>거리</dt><dd>{{ card.restaurant }}에서 직선 {{ card.distance ?? '?' }}m</dd>
            <dt>영업</dt><dd class="unknown">확인 필요</dd>
            <dt>편의시설</dt><dd class="unknown">콘센트·와이파이 확인 필요</dd>
          </dl>
          <div class="actions">
            <a v-if="card.url" class="small" :href="card.url" target="_blank" rel="noopener">카카오맵 상세</a>
            <span v-else class="small muted">상세 링크 정보 없음</span>
            <button v-if="interactive" class="btn choose" :class="{ chosen: card.chosen }" :disabled="card.chosen"
                    @click="emit('chooseCafe', card.course, card.cafeIndex)">
              {{ card.chosen ? '이 코스의 카페로 선택됨' : '이 카페로 코스 선택' }}
            </button>
          </div>
        </template>
      </aside>
    </div>

    <footer class="legend small">
      <span><i class="dot meal" />식당</span>
      <span><i class="dot cafe" />카페</span>
      <span v-if="interactive"><i class="dot alt" />다른 카페 후보</span>
      <span v-if="origin?.kind === 'exit'" class="origin-note"><i class="dot exit" />거리 기준: {{ origin.label }}</span>
      <span><i class="dash" />식당→카페 직선 (실제 경로 아님)</span>
      <span v-if="mode === 'fallback'" class="muted">{{ fallbackReason }}</span>
      <span v-if="link" class="link-note">{{ interactive ? '선택한 코스: ' : '' }}{{ link.cafe }}까지 직선 {{ link.meters }}m</span>
    </footer>

    <ol v-if="mode === 'fallback'" class="place-list small" aria-label="지도 대신 보는 장소 목록">
      <li v-for="(r, i) in recommendations" :key="r.source + r.source_id" :class="{ on: i === selected }">
        <button v-if="interactive" class="linkish" @click="emit('select', i)">{{ i + 1 }}. {{ r.name }}</button>
        <strong v-else>{{ r.name }}</strong>
        <span class="muted"> {{ r.address ?? '주소 정보 없음' }}</span>
        <div v-if="cafeOf(i)" class="muted">☕ {{ cafeOf(i)!.name }} · {{ cafeOf(i)!.road_address ?? cafeOf(i)!.address ?? '주소 정보 없음' }}
          <a v-if="cafeOf(i)!.place_url" :href="cafeOf(i)!.place_url!" target="_blank" rel="noopener">상세</a>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.map-card { background: var(--paper); border: 1px solid var(--line); border-radius: 26px; overflow: hidden; display: flex; flex-direction: column; scroll-margin-top: 80px; }
.stage { position: relative; }
.kakao-map { width: 100%; height: var(--map-h, 340px); }
.mini-map { display: block; width: 100%; height: auto; background: #fbf6ec; }
.link line { stroke: var(--accent); stroke-width: 3; stroke-dasharray: 7 6; }
.link text { fill: var(--accent); font-size: 13px; font-weight: 700; paint-order: stroke; stroke: #fbf6ec; stroke-width: 4px; }
.svg-pin { cursor: pointer; transition: transform .25s ease; outline: none; }
.svg-pin:focus-visible circle { stroke: var(--ink); stroke-width: 4; }
.svg-pin circle { stroke: #fff; stroke-width: 3; }
.svg-pin.meal circle { fill: #f3c7ad; }
.svg-pin.cafe circle { fill: #d9c7b5; }
.svg-pin.alt circle { fill: #fff; stroke: var(--coffee); stroke-width: 2; stroke-dasharray: 3 2; }
.svg-pin.station circle { fill: var(--ink); }
.svg-pin.station { cursor: default; }
.svg-pin.meal.on circle { fill: var(--accent); }
.svg-pin.cafe.on circle { fill: var(--coffee); }
.svg-pin.focused circle { stroke: var(--ink); stroke-width: 4; }
.svg-pin text { font-size: 13px; font-weight: 700; fill: var(--ink); pointer-events: none; }
.svg-pin.on text { fill: #fff; }
.svg-pin .glyph { font-size: 11px; }
.svg-pin .station-label { fill: var(--ink); font-size: 12px; font-weight: 500; }
.place-card { position: absolute; left: 12px; right: 12px; bottom: 12px; max-width: 360px; z-index: 10; background: #fff; border-radius: 20px;
  border: 1px solid var(--line); box-shadow: 0 10px 30px rgba(91, 70, 54, .2); padding: 14px 16px; display: grid; gap: 4px;
  animation: sheet .22s ease; max-height: 70%; overflow: auto; }
.place-card.meal { border-top: 5px solid var(--accent); }
.place-card.cafe { border-top: 5px solid var(--coffee); }
.place-card h4 { margin: 0; font-family: 'Gowun Dodum', sans-serif; font-size: 18px; }
.place-card p { margin: 0; }
.place-card .kind { color: var(--muted); }
.place-card dl { display: grid; grid-template-columns: 64px 1fr; gap: 4px 8px; margin: 6px 0; }
.place-card dt { color: var(--muted); }
.place-card dd { margin: 0; display: flex; flex-wrap: wrap; gap: 4px 10px; }
.place-card .m b { color: var(--accent); }
.unknown { color: var(--warn); }
.close { position: absolute; right: 10px; top: 8px; border: none; background: transparent; font-size: 22px; line-height: 1; color: var(--muted); }
.actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 4px; }
.choose { border-radius: 999px; background: var(--coffee); color: #fff; border-color: var(--coffee); }
.choose.chosen { background: var(--coffee-soft); color: var(--coffee); }
.legend { display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: center; padding: 10px 16px; border-top: 1px solid var(--line); }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
.dot.meal { background: var(--accent); }
.dot.cafe { background: var(--coffee); }
.dot.alt { background: #fff; border: 2px dashed var(--coffee); }
.dot.exit { background: #2f7d5b; border-radius: 3px; }
.svg-pin.exit circle { fill: #2f7d5b; }
.svg-pin.exit { cursor: default; }
:deep(.pin.exit) { background: #2f7d5b; color: #fff; }
.dash { width: 22px; border-top: 3px dashed var(--accent); display: inline-block; }
.link-note { margin-left: auto; font-weight: 500; color: var(--accent); }
.place-list { margin: 0; padding: 10px 16px 14px 16px; list-style: none; display: grid; gap: 6px; border-top: 1px dashed var(--line); }
.place-list li.on .linkish { color: var(--accent); }
.linkish { border: none; background: none; padding: 0; font-weight: 700; color: var(--ink); text-align: left; }
:deep(.pin) { display: inline-flex; align-items: center; gap: 2px; padding: 4px 8px; border-radius: 999px; border: 2px solid #fff;
  background: #fff3ea; box-shadow: 0 3px 10px rgba(91, 70, 54, .25); font-size: 13px; transform: translateY(-4px); transition: transform .2s; }
:deep(.pin.cafe) { background: #f1e7dd; }
:deep(.pin.alt) { background: #fff; border: 2px dashed var(--coffee); padding: 2px 6px; font-size: 11px; opacity: .9; }
:deep(.pin.station) { background: var(--ink); color: #fff; }
:deep(.pin.on) { background: var(--accent); color: #fff; transform: translateY(-8px) scale(1.12); }
:deep(.pin.cafe.on) { background: var(--coffee); }
:deep(.pin.focused) { outline: 3px solid var(--ink); outline-offset: 1px; }
@keyframes sheet { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .svg-pin, :deep(.pin) { transition: none; } .place-card { animation: none; } }
@media (max-width: 600px) { .place-card { max-width: none; } }
</style>
