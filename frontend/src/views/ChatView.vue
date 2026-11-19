<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api, ApiError } from '../api'
import CoursePanel from '../components/CoursePanel.vue'
import RunTimeline from '../components/RunTimeline.vue'
import StatusBanner from '../components/StatusBanner.vue'
import { formatMessage } from '../utils/format'
import { weatherMood } from '../utils/weather'
import type { Area, ChatResponse, RunEvent } from '../types'

interface Turn {
  role: 'user' | 'assistant'
  text: string
  result?: ChatResponse
  error?: string
}

const AREAS: Area[] = ['강남역', '역삼역']
const EXAMPLES = [
  '강남역에서 점심 먹고 카공할 건데 추천해줘',
  '역삼역에서 1만 5천 원 이하로 12시에 점심 먹고 카페 가고 싶어',
  '오늘 비가 오는데 강남역에서 점심 먹고 카공하고 싶어. 많이 걷기는 싫어.',
  '같은 조건에서 한식 말고 일식으로 바꿔줘',
]

const area = ref<Area>('강남역')
const input = ref('')
const turns = ref<Turn[]>([])
const sessionId = ref<string | null>(null)
const busy = ref(false)
const savingIndex = ref<number | null>(null)
const listEl = ref<HTMLElement | null>(null)
const liveEvents = ref<RunEvent[]>([])
const selected = ref(0)
const mobileTab = ref<'chat' | 'course'>('chat')
const mood = computed(() => weatherMood(latest.value?.weather))

// 오른쪽 패널에는 가장 최근의 추천 결과만 보여 준다 (저장·인사 응답은 이전 코스를 유지)
const latest = computed<ChatResponse | null>(() => {
  for (let i = turns.value.length - 1; i >= 0; i--) {
    const r = turns.value[i]!.result
    if (r && r.intent === 'recommend' && !r.clarify) return r
  }
  return null
})
watch(latest, () => { selected.value = 0 })

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
  await send(`${index + 1}번 코스 저장해줘`)
}

function showCourse(index: number) {
  selected.value = index
  mobileTab.value = 'course'
}

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
      <button role="tab" :aria-selected="mobileTab === 'chat'" :class="{ on: mobileTab === 'chat' }" @click="mobileTab = 'chat'">대화</button>
      <button role="tab" :aria-selected="mobileTab === 'course'" :class="{ on: mobileTab === 'course' }" @click="mobileTab = 'course'">
        코스·지도<span v-if="latest?.recommendations.length" class="count">{{ latest.recommendations.length }}</span>
      </button>
    </div>

    <section class="chat" aria-label="대화">
      <div class="toolbar card">
        <div class="area-select" role="radiogroup" aria-label="지역 선택">
          <span class="muted small">지역</span>
          <button v-for="a in AREAS" :key="a" class="area-btn" :class="{ on: area === a }" role="radio"
                  :aria-checked="area === a" @click="area = a">{{ a }}</button>
        </div>
        <button class="btn" @click="newConversation">새 대화</button>
      </div>
      <StatusBanner />

      <div ref="listEl" class="turns">
        <div v-if="!turns.length" class="welcome card">
          <h2>오늘은 어디서 먹고, 어디서 공부할까요?</h2>
          <p class="muted">조건을 말하면 메뉴 가격·영업시간·날씨를 확인해서 식당과 근처 카페를 함께 골라 드려요.
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
                <pre class="msg" v-html="formatMessage(t.text)" />
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

      <form class="composer card" @submit.prevent="send()">
        <input v-model="input" :disabled="busy" maxlength="500"
               :placeholder="`예: ${area}에서 1만원 이하로 점심 먹고 카공`" aria-label="메시지" />
        <button class="btn primary" :disabled="busy || !input.trim()">{{ busy ? '처리 중…' : '보내기' }}</button>
      </form>
    </section>

    <aside class="side">
      <CoursePanel :result="latest" :selected="selected" :saving-index="savingIndex" :busy="busy"
                   @select="selected = $event" @save="saveCourse" />
    </aside>
  </div>
</template>

<style scoped>
.workspace { display: grid; grid-template-columns: minmax(340px, 440px) 1fr; gap: 18px; align-items: start; }
.mobile-tabs { display: none; }
/* 날씨에 따라 코스 영역 바탕을 아주 옅게 물들인다 (응답이 없으면 기본) */
.side { border-radius: 28px; transition: background-color .6s ease; }
.workspace[data-weather='rain'] .side, .workspace[data-weather='snow'] .side, .workspace[data-weather='cold'] .side { background: #f1f3f4; }
.workspace[data-weather='hot'] .side, .workspace[data-weather='clear'] .side { background: #fbf1e2; }
.chat { display: flex; flex-direction: column; gap: 12px; height: calc(100vh - 110px); min-height: 520px; position: sticky; top: 12px; }
.side { min-width: 0; padding: 0 0 24px; }
.toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 10px 14px; }
.area-select { display: flex; align-items: center; gap: 6px; }
.area-btn { border: 1px solid var(--line); background: #fff; border-radius: 999px; padding: 6px 14px; }
.area-btn.on { background: var(--accent); border-color: var(--accent); color: #fff; }
.toolbar > .btn { margin-left: auto; }
.turns { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; padding: 4px; }
.welcome h2 { font-family: 'Gowun Dodum', sans-serif; margin: 0 0 8px; }
.examples { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.example { text-align: left; background: var(--accent-soft); border-color: transparent; }
.bubble { max-width: 90%; border-radius: 18px; padding: 10px 14px; }
.bubble.user { align-self: flex-end; background: var(--ink); color: #fff; border-bottom-right-radius: 6px; }
.bubble.bot { background: var(--paper); border: 1px solid var(--line); border-bottom-left-radius: 6px; }
.msg { margin: 0; white-space: pre-wrap; font-family: inherit; font-size: 14px; line-height: 1.6; }
.answer { display: flex; flex-direction: column; gap: 8px; }
.notices { display: grid; gap: 6px; }
.course-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { border: 1px solid var(--line); background: #fff; border-radius: 999px; padding: 5px 12px; font-size: 13px; }
.chip.on { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); font-weight: 700; }
.chip:disabled { opacity: .55; cursor: default; }
.composer { display: flex; gap: 8px; padding: 8px; }
.composer input { flex: 1; min-width: 0; border: none; outline: none; padding: 10px; background: transparent; }
.composer .btn { white-space: nowrap; flex: none; }

@media (max-width: 900px) {
  .workspace { grid-template-columns: 1fr; }
  .mobile-tabs { display: flex; gap: 6px; background: var(--paper); border: 1px solid var(--line); border-radius: 999px; padding: 4px; position: sticky; top: 8px; z-index: 5; }
  .mobile-tabs button { flex: 1; border: none; background: transparent; border-radius: 999px; padding: 9px; font-weight: 500; color: var(--muted); }
  .mobile-tabs button.on { background: var(--ink); color: #fff; }
  .count { display: inline-grid; place-items: center; min-width: 18px; height: 18px; margin-left: 6px; border-radius: 999px; background: var(--accent); color: #fff; font-size: 11px; }
  .chat { position: static; height: calc(100vh - 150px); }
  .workspace[data-tab='chat'] .side, .workspace[data-tab='course'] .chat { display: none; }
  .bubble { max-width: 100%; }
}
</style>
