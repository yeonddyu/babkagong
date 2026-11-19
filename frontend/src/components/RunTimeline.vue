<script setup lang="ts">
// F3019 실행 단계·Tool 호출 이력·재계획 지점·오류를 실행 순서대로 보여 준다.
import { computed } from 'vue'
import type { RunEvent } from '../types'

const props = defineProps<{ events: RunEvent[]; live?: boolean; elapsedMs?: number }>()

const STAGE: Record<string, string> = {
  analyze: '요청 분석', plan: '작업 계획', execute: 'Tool 실행', judge: '조건 판단', replan: '재계획', respond: '응답 생성', save: '계획 저장',
}
const TOOL: Record<string, string> = {
  search_restaurant_candidates: '음식점 후보 조회', get_restaurant_details: '상세정보 조회',
  search_nearby_cafes: '주변 카페 검색', get_weather_context: '날씨 조회',
}
const CODE: Record<string, string> = {
  MISSING_API_KEY: 'API 키 누락', TIMEOUT: '응답 시간 초과', API_ERROR: '외부 서비스 오류', NO_RESULT: '결과 없음', INVALID_INPUT: '입력 오류',
}

interface Row { key: number; kind: string; title: string; detail?: string; status?: 'ok' | 'bad' | 'warn' | 'info'; ms?: number }

const rows = computed<Row[]>(() => {
  const out: Row[] = []
  for (const e of props.events) {
    const p = e.payload
    if (e.type === 'stage_start') out.push({ key: e.seq, kind: 'stage', title: STAGE[e.stage ?? ''] ?? e.stage ?? '' })
    else if (e.type === 'llm_decision')
      out.push({ key: e.seq, kind: 'decision', title: `판단: ${p.decision}`, detail: `${p.reason} (${p.decided_by === 'llm' ? 'LLM' : '규칙'})`, status: 'info' })
    else if (e.type === 'plan_created')
      out.push({ key: e.seq, kind: 'plan', title: p.mode === 'tools' ? `계획: ${(p.steps as any[]).map((s) => TOOL[s.tool] ?? s.tool).join(' → ')}` : `계획 생략: ${p.reason}`, status: 'info' })
    else if (e.type === 'tool_result')
      out.push({ key: e.seq, kind: 'tool', title: TOOL[p.tool] ?? p.tool, detail: p.ok ? p.summary : CODE[p.error_code] ?? '실패',
                 status: p.ok ? 'ok' : p.error_code === 'NO_RESULT' ? 'warn' : 'bad', ms: p.duration_ms })
    else if (e.type === 'tool_reuse') out.push({ key: e.seq, kind: 'tool', title: `${TOOL[p.tool] ?? p.tool} (이전 결과 재사용)`, status: 'info' })
    else if (e.type === 'replan')
      out.push({ key: e.seq, kind: 'replan', title: `재계획 ${p.count}/${p.limit}회`, detail: `${p.reason} → ${p.detail}`, status: 'warn' })
    else if (e.type === 'stage_end' && e.stage === 'judge')
      out.push({ key: e.seq, kind: 'judge', title: `조건 충족 ${p.satisfied}곳 · 제외 ${p.excluded}곳`, detail: p.stop_reason ?? undefined,
                 status: p.satisfied ? 'ok' : 'warn' })
  }
  return out
})

const toolCount = computed(() => props.events.filter((e) => e.type === 'tool_call').length)
const failCount = computed(() => props.events.filter((e) => e.type === 'tool_result' && !e.payload.ok && e.payload.error_code !== 'NO_RESULT').length)
const replanCount = computed(() => props.events.filter((e) => e.type === 'replan').length)
const current = computed(() => {
  const last = [...props.events].reverse().find((e) => e.type === 'stage_start' || e.type === 'tool_call')
  if (!last) return '요청을 보내는 중'
  return last.type === 'tool_call' ? `${TOOL[last.payload.tool] ?? last.payload.tool} 호출 중` : `${STAGE[last.stage ?? '']} 중`
})
</script>

<template>
  <details class="timeline card" :open="live">
    <summary>
      <span v-if="live" class="spinner" aria-hidden="true" />
      <b>{{ live ? `처리 중 — ${current}` : '실행 과정' }}</b>
      <span class="muted small">
        Tool {{ toolCount }}회<span v-if="replanCount"> · 재계획 {{ replanCount }}회</span><span v-if="failCount"> · 실패 {{ failCount }}건</span>
        <span v-if="elapsedMs"> · {{ (elapsedMs / 1000).toFixed(1) }}초</span>
      </span>
    </summary>
    <ol>
      <li v-for="r in rows" :key="r.key" :class="[r.kind, r.status]">
        <span class="dot" />
        <div>
          <div class="row-title">{{ r.title }} <span v-if="r.ms !== undefined" class="muted small">{{ r.ms }}ms</span></div>
          <div v-if="r.detail" class="small muted">{{ r.detail }}</div>
        </div>
      </li>
    </ol>
  </details>
</template>

<style scoped>
.timeline summary { cursor: pointer; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
ol { list-style: none; margin: 10px 0 0; padding: 0 0 0 6px; border-left: 2px solid var(--line); display: grid; gap: 6px; }
li { position: relative; display: flex; gap: 10px; padding-left: 10px; font-size: 14px; }
.dot { position: absolute; left: -12px; top: 6px; width: 10px; height: 10px; border-radius: 50%; background: var(--line); }
li.stage .row-title { font-weight: 700; color: var(--coffee); }
li.ok .dot { background: var(--ok); }
li.bad .dot { background: var(--bad); }
li.bad .row-title { color: var(--bad); }
li.warn .dot { background: var(--warn); }
li.info .dot { background: var(--coffee); }
li.replan { background: var(--warn-soft); border-radius: 8px; padding: 6px 10px; }
.spinner { width: 14px; height: 14px; border: 2px solid var(--accent-soft); border-top-color: var(--accent); border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
