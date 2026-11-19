<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, ApiError } from '../api'
import RecommendationCard from '../components/RecommendationCard.vue'
import type { Area, ChatResponse } from '../types'

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

async function send(text?: string) {
  const message = (text ?? input.value).trim()
  if (!message || busy.value) return
  input.value = ''
  turns.value.push({ role: 'user', text: message })
  busy.value = true
  scroll()
  try {
    const result = await api.chat(message, sessionId.value, area.value)
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
  <section class="chat">
    <div class="toolbar card">
      <div class="area-select" role="radiogroup" aria-label="지역 선택">
        <span class="muted small">지역</span>
        <button v-for="a in AREAS" :key="a" class="area-btn" :class="{ on: area === a }" role="radio"
                :aria-checked="area === a" @click="area = a">{{ a }}</button>
      </div>
      <slot name="status" />
      <button class="btn" @click="newConversation">새 대화</button>
    </div>

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
              <pre class="msg">{{ t.text }}</pre>
              <p v-if="t.result.saved_plan" class="small">
                <RouterLink :to="`/plans/${t.result.saved_plan.id}`">저장한 계획 보기 →</RouterLink>
              </p>
            </div>
            <div v-if="t.result.notices.length" class="notices">
              <div v-for="n in t.result.notices" :key="n" class="notice warn">ℹ {{ n }}</div>
            </div>
            <div v-if="t.result.recommendations.length" class="recs">
              <RecommendationCard v-for="(r, ri) in t.result.recommendations" :key="r.source + r.source_id" :rec="r"
                                  :index="ri" :saving="busy && savingIndex === ri" @save="saveCourse" />
            </div>
            <details v-if="t.result.criteria.length || t.result.excluded.length" class="card small basis">
              <summary>판단 기준과 제외한 후보 ({{ t.result.excluded.length }})</summary>
              <ul><li v-for="c in t.result.criteria" :key="c">{{ c }}</li></ul>
              <ul v-if="t.result.weather_policy.length"><li v-for="w in t.result.weather_policy" :key="w">🌤 {{ w }}</li></ul>
              <ul class="excluded"><li v-for="x in t.result.excluded" :key="x.source + x.source_id"><b>{{ x.name }}</b> — {{ x.reason }}</li></ul>
            </details>
            <slot name="run" :result="t.result" />
          </template>
        </div>
      </template>
      <slot name="busy" :busy="busy" />
    </div>

    <form class="composer card" @submit.prevent="send()">
      <input v-model="input" :disabled="busy" maxlength="500"
             :placeholder="`예: ${area}에서 1만원 이하로 점심 먹고 카공`" aria-label="메시지" />
      <button class="btn primary" :disabled="busy || !input.trim()">{{ busy ? '처리 중…' : '보내기' }}</button>
    </form>
  </section>
</template>

<style scoped>
.chat { display: flex; flex-direction: column; gap: 12px; height: calc(100vh - 110px); min-height: 520px; }
.toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 10px 14px; }
.area-select { display: flex; align-items: center; gap: 6px; }
.area-btn { border: 1px solid var(--line); background: #fff; border-radius: 999px; padding: 6px 14px; }
.area-btn.on { background: var(--accent); border-color: var(--accent); color: #fff; }
.toolbar > .btn { margin-left: auto; }
.turns { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; padding: 4px; }
.welcome h2 { font-family: 'Gowun Dodum', sans-serif; margin: 0 0 8px; }
.examples { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.example { text-align: left; background: var(--accent-soft); border-color: transparent; }
.bubble { max-width: 85%; border-radius: 16px; padding: 10px 14px; }
.bubble.user { align-self: flex-end; background: var(--ink); color: #fff; }
.bubble.bot { background: var(--paper); border: 1px solid var(--line); }
.msg { margin: 0; white-space: pre-wrap; font-family: inherit; font-size: 14px; line-height: 1.6; }
.answer { display: flex; flex-direction: column; gap: 10px; }
.notices { display: grid; gap: 6px; }
.recs { display: grid; gap: 12px; }
.basis summary { cursor: pointer; font-weight: 500; }
.basis ul { margin: 8px 0; padding-left: 18px; }
.excluded { color: var(--muted); }
.composer { display: flex; gap: 8px; padding: 8px; }
.composer input { flex: 1; border: none; outline: none; padding: 10px; background: transparent; }
@media (max-width: 600px) { .bubble { max-width: 100%; } .chat { height: auto; } }
</style>
