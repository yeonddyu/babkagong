<script setup lang="ts">
// F3019 API 키 누락·LLM 미사용 상태 안내 (키 값은 서버가 보내지 않으며 표시하지도 않는다)
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import type { Health } from '../types'

const LABEL: Record<string, string> = {
  REDTABLE_API_KEY: '서울관광재단 음식관광(메뉴·가격·영업시간)',
  SEOUL_OPENAPI_KEY: '서울 열린데이터광장(인허가·보조 카페)',
  KAKAO_REST_API_KEY: '카카오 로컬(카페 검색)',
  KMA_API_KEY: '기상청 날씨',
}

const health = ref<Health | null>(null)
const down = ref(false)
const missing = computed(() => Object.entries(health.value?.api_keys ?? {})
  .filter(([k, v]) => !v && k in LABEL).map(([k]) => LABEL[k]))

onMounted(async () => {
  try {
    health.value = await api.health()
  } catch {
    down.value = true
  }
})
</script>

<template>
  <div v-if="down" class="notice bad small">서버에 연결할 수 없어요. 백엔드가 실행 중인지 확인해 주세요.</div>
  <template v-else-if="health">
    <div v-if="missing.length" class="notice warn small" role="status">
      API 키가 설정되지 않은 기능: {{ missing.join(', ') }} — 해당 정보는 확인하지 못한 채로 추천해요.
    </div>
    <div v-if="!health.llm.available" class="notice warn small" role="status">
      AI 모델({{ health.llm.provider.toUpperCase() }})을 사용할 수 없어 요청 분석과 응답 문장은 규칙 기반으로 처리해요.
    </div>
  </template>
</template>
