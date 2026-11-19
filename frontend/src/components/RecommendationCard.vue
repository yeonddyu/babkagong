<script setup lang="ts">
import type { Recommendation } from '../types'

defineProps<{ rec: Recommendation; index: number; saving?: boolean }>()
defineEmits<{ save: [index: number] }>()

const won = (v: number | null) => (v ? `${v.toLocaleString()}원` : '가격 미확인')
const resultClass = (r: string) => (r === 'pass' ? 'ok' : r === 'fail' ? 'bad' : 'warn')
const resultLabel = (r: string) => (r === 'pass' ? '충족' : r === 'fail' ? '불충족' : '미확인')
const sourceLabel = (s: string) =>
  ({
    seoul_tourism_redtable: '서울관광재단',
    gangnam_general_restaurant_license: '강남구 인허가',
    kakao_local_category_CE7: '카카오맵',
    gangnam_rest_food_license: '강남구 휴게음식점',
  })[s] ?? s
</script>

<template>
  <article class="rec card">
    <div class="rec-head">
      <span class="rank">{{ index + 1 }}</span>
      <div class="title">
        <h3>{{ rec.name }}</h3>
        <p class="muted small">
          {{ rec.address ?? '주소 미확인' }} · {{ rec.food_type ?? rec.category ?? '분류 미확인' }}
          <span class="pill neutral">{{ sourceLabel(rec.source) }} #{{ rec.source_id }}</span>
        </p>
      </div>
      <button class="btn primary save" :disabled="saving" @click="$emit('save', index)">
        {{ saving ? '저장 중…' : '이 코스 저장' }}
      </button>
    </div>

    <div class="facts">
      <div>
        <span class="label">거리</span>
        <strong v-if="rec.distance_m !== null">역에서 직선 {{ rec.distance_m }}m</strong>
        <span v-else>미확인</span>
        <span v-if="rec.estimated_walk_minutes" class="muted small"> · 도보 약 {{ rec.estimated_walk_minutes }}분(추정)</span>
      </div>
      <div>
        <span class="label">영업</span>
        <span>{{ rec.business_hours ?? '영업시간 미확인' }}</span>
      </div>
      <div v-if="rec.matched_menus.length">
        <span class="label">메뉴</span>
        <span>
          <template v-for="(m, i) in rec.matched_menus.slice(0, 3)" :key="m.name">
            {{ i ? ' · ' : '' }}{{ m.name }} <b>{{ won(m.price_krw) }}</b>
          </template>
        </span>
      </div>
    </div>

    <ul class="checks">
      <li v-for="c in rec.checks" :key="c.criterion">
        <span class="pill" :class="resultClass(c.result)">{{ c.criterion }} {{ resultLabel(c.result) }}</span>
        <span class="small">{{ c.value }}</span>
        <span class="muted small" v-if="c.basis"> — {{ c.basis }}</span>
      </li>
    </ul>

    <ul v-if="rec.unverified.length" class="unverified">
      <li v-for="u in rec.unverified" :key="u" class="small">⚠ {{ u }}</li>
    </ul>

    <section class="cafes">
      <h4>☕ 식사 후 카공 카페</h4>
      <p v-if="!rec.cafes.length" class="muted small">{{ rec.cafe_notice ?? '주변 카페를 찾지 못했어요.' }}</p>
      <ul v-else>
        <li v-for="c in rec.cafes" :key="c.source + c.source_id">
          <div>
            <a v-if="c.place_url" :href="c.place_url" target="_blank" rel="noopener">{{ c.name }}</a>
            <strong v-else>{{ c.name }}</strong>
            <span class="muted small"> · {{ c.road_address ?? c.address ?? '주소 미확인' }}</span>
          </div>
          <div class="small">
            식당에서 직선 {{ c.distance_m ?? '?' }}m<span v-if="c.estimated_walk_minutes"> · 도보 약 {{ c.estimated_walk_minutes }}분(추정)</span>
            <span class="pill neutral">{{ sourceLabel(c.source) }}</span>
          </div>
        </li>
      </ul>
      <p class="muted small">카페 영업시간·콘센트·와이파이·혼잡도는 데이터로 확인할 수 없어요.</p>
    </section>

    <details class="score small">
      <summary>추천 점수 {{ rec.score }}</summary>
      <ul><li v-for="r in rec.score_reasons" :key="r">{{ r }}</li></ul>
    </details>
  </article>
</template>

<style scoped>
.rec { display: flex; flex-direction: column; gap: 12px; }
.rec-head { display: flex; gap: 12px; align-items: flex-start; }
.rank { width: 32px; height: 32px; flex: none; border-radius: 50%; background: var(--accent-soft); color: var(--accent); display: grid; place-items: center; font-weight: 700; }
.title { flex: 1; min-width: 0; }
.title h3 { margin: 0; font-size: 18px; }
.title p { margin: 4px 0 0; }
.save { flex: none; }
.facts { display: grid; gap: 6px; font-size: 14px; }
.label { display: inline-block; width: 40px; color: var(--muted); font-size: 12px; }
.checks, .unverified, .cafes ul, .score ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 4px; }
.unverified { color: var(--warn); }
.cafes { background: var(--coffee-soft); border-radius: 10px; padding: 10px 12px; }
.cafes h4 { margin: 0 0 6px; font-size: 14px; color: var(--coffee); }
.cafes li { padding: 6px 0; border-bottom: 1px dashed var(--line); }
.cafes p { margin: 6px 0 0; }
.score summary { cursor: pointer; color: var(--muted); }
@media (max-width: 600px) { .rec-head { flex-wrap: wrap; } .save { width: 100%; } }
</style>
