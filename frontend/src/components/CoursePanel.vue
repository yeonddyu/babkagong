<script setup lang="ts">
// 오른쪽 패널: 가장 최근 추천 결과의 코스(식당+카페)를 보여 준다. 대화 기록과 분리해 같은 목록을 두 번 쓰지 않는다.
import CourseTimeline from './CourseTimeline.vue'
import MapPanel from './MapPanel.vue'
import MenuRoulette from './MenuRoulette.vue'
import RecommendationCard from './RecommendationCard.vue'
import WeatherStrip from './WeatherStrip.vue'
import type { ChatResponse } from '../types'

defineProps<{ result: ChatResponse | null; selected: number; savingIndex: number | null; busy: boolean }>()
defineEmits<{ select: [index: number]; save: [index: number] }>()
</script>

<template>
  <section class="course-panel" aria-label="추천 코스">
    <slot name="top" />
    <div v-if="!result" class="empty card">
      <p class="empty-title">아직 고른 코스가 없어요</p>
      <p class="muted small">왼쪽에서 지역과 조건을 말하면, 식당과 식사 후 갈 카페를 이곳에 모아 보여 드려요.</p>
    </div>
    <template v-else>
      <WeatherStrip :weather="result.weather" :policy="result.weather_policy" />
      <MapPanel v-if="result.recommendations.length" :recommendations="result.recommendations" :selected="selected"
                @select="$emit('select', $event)" />
      <CourseTimeline v-if="result.recommendations[selected]" :rec="result.recommendations[selected]!" :index="selected"
                      :conditions="result.conditions" />
      <div v-if="!result.recommendations.length" class="empty card">
        <p class="empty-title">조건에 맞는 코스를 찾지 못했어요</p>
        <p v-if="result.stop_reason" class="small">{{ result.stop_reason }}</p>
        <ul v-if="result.suggestions.length" class="small">
          <li v-for="s in result.suggestions" :key="s">{{ s }}</li>
        </ul>
      </div>
      <div v-else class="recs">
        <div v-for="(r, ri) in result.recommendations" :key="r.source + r.source_id"
             class="rec-wrap" :class="{ on: selected === ri }" @click="$emit('select', ri)">
          <RecommendationCard :rec="r" :index="ri" :saving="busy && savingIndex === ri" @save="$emit('save', $event)" />
        </div>
      </div>
      <MenuRoulette :recommendations="result.recommendations" @select="$emit('select', $event)" />
      <details v-if="result.criteria.length || result.excluded.length" class="card small basis">
        <summary>판단 기준과 제외한 후보 ({{ result.excluded.length }})</summary>
        <ul><li v-for="c in result.criteria" :key="c">{{ c }}</li></ul>
        <ul v-if="result.weather_policy.length"><li v-for="w in result.weather_policy" :key="w">날씨 반영: {{ w }}</li></ul>
        <ul class="excluded"><li v-for="x in result.excluded" :key="x.source + x.source_id"><b>{{ x.name }}</b> — {{ x.reason }}</li></ul>
      </details>
    </template>
  </section>
</template>

<style scoped>
.course-panel { display: flex; flex-direction: column; gap: 14px; }
.empty { text-align: left; padding: 24px; }
.empty-title { font-family: 'Gowun Dodum', sans-serif; font-size: 20px; margin: 0 0 6px; }
.recs { display: grid; gap: 14px; }
.rec-wrap { border-radius: 22px; outline: 3px solid transparent; outline-offset: 2px; transition: outline-color .2s; cursor: pointer; }
.rec-wrap.on { outline-color: var(--accent); }
.basis summary { cursor: pointer; font-weight: 500; }
.basis ul { margin: 8px 0; padding-left: 18px; }
.excluded { color: var(--muted); }
</style>
