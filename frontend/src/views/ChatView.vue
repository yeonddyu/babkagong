<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api, ApiError } from '../api'
import CoursePanel from '../components/CoursePanel.vue'
import MapPanel from '../components/MapPanel.vue'
import RunTimeline from '../components/RunTimeline.vue'
import StatusBanner from '../components/StatusBanner.vue'
import { formatMessage } from '../utils/format'
import { weatherMood } from '../utils/weather'
import WeatherMascot from '../components/WeatherMascot.vue'
import { chooseCafe, chosenCafeIndex, courseState, focusPlace, resetCourse, selectCourse } from '../stores/course'
import type { Area, ChatResponse, RunEvent } from '../types'

interface Turn {
  role: 'user' | 'assistant'
  text: string
  result?: ChatResponse
  error?: string
}

const QUICK_AREAS: Area[] = ['강남역', '역삼역'] // 자주 쓰는 역 (나머지는 역 검색)
const EXAMPLES = [
  '강남역에서 점심 먹고 카공할 건데 추천해줘',
  '역삼역에서 1만 5천 원 이하로 12시에 점심 먹고 카페 가고 싶어',
  '오늘 비가 오는데 강남역에서 점심 먹고 카공하고 싶어. 많이 걷기는 싫어.',
  '홍대입구역 근처에서 1만원 이하로 점심 먹고 카공',
  '같은 조건에서 한식 말고 일식으로 바꿔줘',
]

const area = ref<Area>('강남역')
// 역 검색: 서버의 역 목록(서울 지하철역)에서 고른다. 목록에 없는 이름은 받지 않는다.
const stationNames = ref<string[]>([...QUICK_AREAS])
const stationQuery = ref('')
const areaError = ref('')
api.stations().then((r) => { stationNames.value = r.stations.map((s) => s.name) }).catch(() => { /* 목록을 못 받으면 기본 두 역 */ })
function pickArea(name: string) {
  const q = name.trim()
  if (!q) return
  const hit = stationNames.value.find((s) => s === q) ?? stationNames.value.find((s) => s === `${q}역` || s.startsWith(`${q}역(`))
  if (!hit) {
    areaError.value = `'${q}' 은(는) 역 목록에 없어요. 서울 지하철역 이름으로 골라 주세요.`
    return
  }
  areaError.value = ''
  area.value = hit
  stationQuery.value = QUICK_AREAS.includes(hit) ? '' : hit
}
const input = ref('')
const turns = ref<Turn[]>([])
const sessionId = ref<string | null>(null)
const busy = ref(false)
const savingIndex = ref<number | null>(null)
const listEl = ref<HTMLElement | null>(null)
const liveEvents = ref<RunEvent[]>([])
const selected = computed(() => courseState.selected)
const mobileTab = ref<'chat' | 'map'>('chat')
const mood = computed(() => weatherMood(latest.value?.weather))

// 오른쪽 패널에는 가장 최근의 추천 결과만 보여 준다 (저장·인사 응답은 이전 코스를 유지)
const latest = computed<ChatResponse | null>(() => {
  for (let i = turns.value.length - 1; i >= 0; i--) {
    const r = turns.value[i]!.result
    if (r && r.intent === 'recommend' && !r.clarify) return r
  }
  return null
})
watch(latest, () => { resetCourse() })

async function send(text?: string) {
  const message = (text ?? input.value).trim()
  if (!message || busy.value) return
  input.value = ''
  turns.value.push({ role: 'user', text: message })
  busy.value = true
  liveEvents.value = []
  scroll()
  try {
    const result = await api.chatStream(message, sessionId.value, area.value, (e) => {
      liveEvents.value.push(e)
      scroll()
    })
    sessionId.value = result.session_id
    turns.value.push({ role: 'assistant', text: result.message, result })
  } catch (e) {
    turns.value.push({ role: 'assistant', text: '', error: e instanceof ApiError ? e.message : '알 수 없는 오류가 발생했어요.' })
  } finally {
    busy.value = false
    savingIndex.value = null
    scroll()
  }
}

async function saveCourse(index: number) {
  savingIndex.value = index
  // 지도·카드에서 고른 카페로 저장 (F3015 저장은 대화 흐름을 그대로 사용)
  await send(`${index + 1}번 코스 저장해줘 (카페 ${chosenCafeIndex(index) + 1}번)`)
}

const isMobile = () => typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 900px)').matches
const smooth = (): ScrollBehavior =>
  typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'

// 대화의 코스 칩: 그 코스를 고르고 아래 추천 카드로 이동 (지도는 공통 상태로 함께 바뀜)
async function showCourse(index: number) {
  selectCourse(index)
  await nextTick()
  document.getElementById(`course-${index}`)?.scrollIntoView?.({ behavior: smooth(), block: 'start' })
}

// 모바일: 지도에서 보기 요청이 오면 지도 탭으로 전환
function showMap() {
  mobileTab.value = 'map'
  window.scrollTo?.({ top: 0, behavior: smooth() })
}
watch(() => courseState.focus, (f) => { if (f && isMobile()) showMap() })

function newConversation() {
  turns.value = []
  sessionId.value = null
}

async function scroll() {
  await nextTick()
  const el = listEl.value
  if (el && typeof el.scrollTo === 'function') el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
}
</script>

<template>
  <div class="workspace" :data-tab="mobileTab" :data-weather="mood ?? 'none'">
    <div class="mobile-tabs" role="tablist" aria-label="화면 전환">
      <button role="tab" :aria-selected="mobileTab === 'chat'" :class="{ on: mobileTab === 'chat' }" @click="mobileTab = 'chat'">대화·추천</button>
      <button role="tab" :aria-selected="mobileTab === 'map'" :class="{ on: mobileTab === 'map' }" @click="mobileTab = 'map'">
        지도<span v-if="latest?.recommendations.length" class="count">{{ latest.recommendations.length }}</span>
      </button>
    </div>

    <div class="left">
      <WeatherMascot :weather="latest?.weather" :has-result="!!latest" :policy="latest?.weather_policy" />
      <div class="toolbar card">
        <div class="area-select" aria-label="지역 선택">
          <span class="muted small">지역</span>
          <button v-for="a in QUICK_AREAS" :key="a" class="area-btn" :class="{ on: area === a }" :aria-pressed="area === a"
                  @click="pickArea(a)">{{ a }}</button>
          <form class="station-search" @submit.prevent="pickArea(stationQuery)">
            <input v-model="stationQuery" list="station-list" :placeholder="QUICK_AREAS.includes(area) ? '다른 역 검색' : area"
                   aria-label="다른 역 검색" maxlength="30" :class="{ on: !QUICK_AREAS.includes(area) }" @change="pickArea(stationQuery)" />
            <datalist id="station-list">
              <option v-for="s in stationNames" :key="s" :value="s" />
            </datalist>
          </form>
          <span v-if="areaError" class="small area-error" role="alert">{{ areaError }}</span>
        </div>
        <button class="btn" @click="newConversation">새 대화</button>
      </div>
      <StatusBanner />

      <section class="chat card" aria-label="대화">
        <div ref="listEl" class="turns">
          <div v-if="!turns.length" class="welcome">
            <h2>오늘은 어디서 먹고, 어디서 공부할까요?</h2>
            <p class="muted">서울 지하철역 주변에서, 조건을 말하면 메뉴 가격·영업시간·날씨를 확인해서 식당과 근처 카페를 함께 골라 드려요.
              확인되지 않은 정보는 ‘미확인’으로 표시해요.</p>
            <div class="examples">
              <button v-for="ex in EXAMPLES" :key="ex" class="btn example" @click="send(ex)">{{ ex }}</button>
            </div>
          </div>

          <template v-for="(t, i) in turns" :key="i">
            <div v-if="t.role === 'user'" class="bubble user">{{ t.text }}</div>
            <div v-else class="answer">
              <div v-if="t.error" class="notice bad">{{ t.error }}</div>
              <template v-else-if="t.result">
                <div class="bubble bot">
                  <!-- 대화창은 짧게: 요약이 있으면 요약만, 전체 답변은 펼쳐서 -->
                  <template v-if="t.result.summary">
                    <pre class="msg summary" v-html="formatMessage(t.result.summary)" />
                    <details class="full">
                      <summary>전체 답변 보기</summary>
                      <pre class="msg" v-html="formatMessage(t.text)" />
                    </details>
                  </template>
                  <pre v-else class="msg" v-html="formatMessage(t.text)" />
                  <p v-if="t.result.saved_plan" class="small">
                    <RouterLink :to="`/plans/${t.result.saved_plan.id}`">저장한 계획 보기</RouterLink>
                  </p>
                </div>
                <div v-if="t.result.notices.length" class="notices">
                  <div v-for="n in t.result.notices" :key="n" class="notice warn">{{ n }}</div>
                </div>
                <div v-if="t.result.recommendations.length" class="course-chips" aria-label="이 답변의 코스">
                  <button v-for="(r, ri) in t.result.recommendations" :key="r.source + r.source_id" class="chip"
                          :class="{ on: t.result === latest && selected === ri }" :disabled="t.result !== latest"
                          @click="showCourse(ri)">
                    {{ ri + 1 }}. {{ r.name }}
                  </button>
                </div>
                <RunTimeline :events="t.result.events" :elapsed-ms="t.result.elapsed_ms" />
              </template>
            </div>
          </template>
          <RunTimeline v-if="busy" :events="liveEvents" live />
        </div>

        <form class="composer" @submit.prevent="send()">
          <input v-model="input" :disabled="busy" maxlength="500"
                 :placeholder="`예: ${area}에서 1만원 이하로 점심 먹고 카공`" aria-label="메시지" />
          <button class="btn primary" :disabled="busy || !input.trim()">{{ busy ? '처리 중…' : '보내기' }}</button>
        </form>
      </section>

      <CoursePanel :result="latest" :selected="selected" :saving-index="savingIndex" :busy="busy"
                   @select="selectCourse" @save="saveCourse" @more="send('다른 곳 더 보여줘')" @show-map="showMap" />
    </div>

    <aside class="mapside" aria-label="지도">
      <MapPanel v-if="latest?.recommendations.length" :recommendations="latest.recommendations" :selected="selected"
                :cafe-choice="courseState.cafeChoice" :focus="courseState.focus" :origin="latest.origin"
                @select="selectCourse" @focus="focusPlace" @choose-cafe="chooseCafe" />
      <div v-else class="map-empty card">
        <p class="empty-title">아직 고른 코스가 없어요</p>
        <p class="muted small">왼쪽에서 지역과 조건을 말하면, 식당과 식사 후 갈 카페를 이 지도에 표시해 드려요.</p>
      </div>
    </aside>
  </div>
</template>

<style scoped>
/* 데스크톱: 왼쪽 45 (마스코트·대화·룰렛·카드) / 오른쪽 55 (따라오는 지도) */
.workspace { display: grid; grid-template-columns: minmax(0, 45fr) minmax(0, 55fr); gap: 20px; align-items: start; }
.mobile-tabs { display: none; }
.left { display: flex; flex-direction: column; gap: 12px; min-width: 0; padding-bottom: 24px; }
.mapside { position: sticky; top: 12px; min-width: 0; --map-h: max(360px, calc(100vh - 250px)); }
.map-empty { min-height: 360px; display: grid; align-content: center; padding: 28px; border-radius: 26px;
  background: repeating-linear-gradient(45deg, var(--paper), var(--paper) 14px, #fbf4ea 14px, #fbf4ea 28px); }
.empty-title { font-family: 'Gowun Dodum', sans-serif; font-size: 20px; margin: 0 0 6px; }
.toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 10px 14px; }
.area-select { display: flex; align-items: center; gap: 6px; }
.area-btn { border: 1px solid var(--line); background: #fff; border-radius: 999px; padding: 6px 14px; }
.area-btn.on { background: var(--accent); border-color: var(--accent); color: #fff; }
.station-search input { width: 9.5em; border: 1px solid var(--line); border-radius: 999px; padding: 6px 12px; background: #fff; }
.station-search input.on { border-color: var(--accent); background: var(--accent-soft); font-weight: 700; }
.area-error { color: var(--warn); flex-basis: 100%; }
.toolbar > .btn { margin-left: auto; }
.chat { display: flex; flex-direction: column; gap: 8px; padding: 10px; border-radius: 22px; }
.turns { max-height: min(56vh, 560px); min-height: 220px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; padding: 4px; }
.welcome h2 { font-family: 'Gowun Dodum', sans-serif; margin: 0 0 8px; }
.examples { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.example { text-align: left; background: var(--accent-soft); border-color: transparent; }
.bubble { max-width: 90%; border-radius: 18px; padding: 10px 14px; }
.bubble.user { align-self: flex-end; background: var(--ink); color: #fff; border-bottom-right-radius: 6px; }
.bubble.bot { background: #fff; border: 1px solid var(--line); border-bottom-left-radius: 6px; }
.msg { margin: 0; white-space: pre-wrap; font-family: inherit; font-size: 14px; line-height: 1.6; }
.full { margin-top: 6px; }
.full summary { cursor: pointer; font-size: 13px; color: var(--accent); }
.full .msg { margin-top: 6px; padding-top: 6px; border-top: 1px dashed var(--line); color: var(--muted); font-size: 13px; }
.answer { display: flex; flex-direction: column; gap: 8px; }
.notices { display: grid; gap: 6px; }
.course-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { border: 1px solid var(--line); background: #fff; border-radius: 999px; padding: 5px 12px; font-size: 13px; }
.chip.on { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); font-weight: 700; }
.chip:disabled { opacity: .55; cursor: default; }
.composer { display: flex; gap: 8px; padding: 6px; border: 1px solid var(--line); border-radius: 16px; background: #fff; }
.composer input { flex: 1; min-width: 0; border: none; outline: none; padding: 10px; background: transparent; }
.composer:focus-within { border-color: var(--accent); }
.composer .btn { white-space: nowrap; flex: none; }

@media (max-width: 900px) {
  .workspace { grid-template-columns: 1fr; }
  .mobile-tabs { display: flex; gap: 6px; background: var(--paper); border: 1px solid var(--line); border-radius: 999px; padding: 4px; position: sticky; top: 8px; z-index: 5; }
  .mobile-tabs button { flex: 1; border: none; background: transparent; border-radius: 999px; padding: 9px; font-weight: 500; color: var(--muted); }
  .mobile-tabs button.on { background: var(--ink); color: #fff; }
  .count { display: inline-grid; place-items: center; min-width: 18px; height: 18px; margin-left: 6px; border-radius: 999px; background: var(--accent); color: #fff; font-size: 11px; }
  .workspace[data-tab='chat'] .mapside, .workspace[data-tab='map'] .left { display: none; }
  .mapside { position: static; --map-h: 58vh; }
  /* 모바일 대화 탭: 입력창을 화면 아래에 고정해 카드까지 내려가도 바로 입력 */
  .left { padding-bottom: 84px; }
  .composer { position: fixed; left: 12px; right: 12px; bottom: 12px; z-index: 6; box-shadow: 0 8px 24px -10px rgba(60, 40, 20, .35); }
  .turns { max-height: 60vh; }
  .bubble { max-width: 100%; }
}
</style>
