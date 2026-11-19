<script setup lang="ts">
// 추천 코스 카드: 식당 핵심 정보(거리·영업·예산 내 메뉴)와 대표 카페를 한눈에, 근거와 다른 카페는 접어 둔다.
// 확인되지 않은 값은 '미확인'으로만 표시한다.
import { computed } from 'vue'
import type { Recommendation } from '../types'

const props = withDefaults(defineProps<{ rec: Recommendation; index: number; saving?: boolean; cafeIndex?: number }>(), { cafeIndex: 0 })
const emit = defineEmits<{
  save: [index: number]
  chooseCafe: [course: number, cafe: number]
  focus: [f: { kind: 'meal' | 'cafe'; course: number; cafe: number }]
}>()

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

const chosen = computed(() => (props.rec.cafes[props.cafeIndex] ? props.cafeIndex : 0))
const mainCafe = computed(() => props.rec.cafes[chosen.value] ?? null)
// 예산 조건이 있으면 예산 내 메뉴, 없으면 가격이 확인된 대표 메뉴
const menus = computed(() => (props.rec.matched_menus.length ? props.rec.matched_menus : props.rec.sample_menus ?? []))
const menuLabel = computed(() => (props.rec.matched_menus.length ? '예산 안 메뉴' : '대표 메뉴'))
const otherCafes = computed(() => props.rec.cafes.map((c, i) => ({ c, i })).filter(({ i }) => i !== chosen.value))
</script>

<template>
  <article class="rec card">
    <header class="rec-head">
      <span class="rank" aria-hidden="true">{{ index + 1 }}</span>
      <div class="title">
        <h3>{{ rec.name }}</h3>
        <p class="muted small">{{ rec.address ?? '주소 미확인' }}</p>
      </div>
      <button class="btn primary save" :disabled="saving" @click.stop="emit('save', index)">
        {{ saving ? '저장 중…' : '이 코스 저장' }}
      </button>
    </header>

    <div class="facts">
      <span class="fact">
        <template v-if="rec.distance_m !== null">역에서 직선 {{ rec.distance_m }}m</template>
        <template v-else>거리 미확인</template>
        <span v-if="rec.estimated_walk_minutes" class="muted"> · 도보 약 {{ rec.estimated_walk_minutes }}분(추정)</span>
      </span>
      <span class="fact" :class="{ unknown: !rec.business_hours }">{{ rec.business_hours ?? '영업시간 미확인' }}</span>
      <span class="fact tag">{{ rec.food_type ?? rec.category ?? '분류 미확인' }}</span>
    </div>

    <ul v-if="menus.length" class="menus" :aria-label="menuLabel">
      <li v-for="m in menus.slice(0, 3)" :key="m.name" class="menu">{{ m.name }} <b>{{ won(m.price_krw) }}</b></li>
    </ul>
    <p v-else class="no-menu small">메뉴·가격 정보 없음</p>

    <div class="checks" aria-label="조건 판단">
      <span v-for="c in rec.checks" :key="c.criterion" class="pill" :class="resultClass(c.result)" :title="c.value">
        {{ c.criterion }} {{ resultLabel(c.result) }}
      </span>
    </div>

    <ul v-if="rec.unverified.length" class="unverified">
      <li v-for="u in rec.unverified" :key="u" class="small">{{ u }}</li>
    </ul>

    <button class="btn map-btn small" @click.stop="emit('focus', { kind: 'meal', course: index, cafe: chosen })">지도에서 식당 보기</button>

    <section class="cafes">
      <h4>식사 후 카공 카페</h4>
      <p v-if="!mainCafe" class="muted small">{{ rec.cafe_notice ?? '주변 카페를 찾지 못했어요.' }}</p>
      <div v-else class="main-cafe">
        <span class="cup" aria-hidden="true">☕</span>
        <div>
          <a v-if="mainCafe.place_url" :href="mainCafe.place_url" target="_blank" rel="noopener" @click.stop>{{ mainCafe.name }}</a>
          <strong v-else>{{ mainCafe.name }}</strong>
          <div class="small muted">
            식당에서 직선 {{ mainCafe.distance_m ?? '?' }}m<span v-if="mainCafe.estimated_walk_minutes"> · 도보 약 {{ mainCafe.estimated_walk_minutes }}분(추정)</span>
            · {{ sourceLabel(mainCafe.source) }}
          </div>
          <div class="small cafe-facts"><span class="unknown">영업시간 확인 필요</span> · <span class="unknown">콘센트·와이파이 확인 필요</span></div>
        </div>
        <button class="btn map-btn small" @click.stop="emit('focus', { kind: 'cafe', course: index, cafe: chosen })">지도 보기</button>
      </div>
      <details v-if="otherCafes.length" class="more small" @click.stop>
        <summary>근처 카페 {{ otherCafes.length }}곳 더 보기</summary>
        <ul>
          <li v-for="{ c, i } in otherCafes" :key="c.source + c.source_id">
            <a v-if="c.place_url" :href="c.place_url" target="_blank" rel="noopener">{{ c.name }}</a>
            <strong v-else>{{ c.name }}</strong>
            <span class="muted"> · 직선 {{ c.distance_m ?? '?' }}m · {{ c.road_address ?? c.address ?? '주소 미확인' }}</span>
            <button class="btn tiny" @click.stop="emit('chooseCafe', index, i)">이 카페로 바꾸기</button>
          </li>
        </ul>
      </details>
      <p class="muted small note">카페 영업시간·콘센트·와이파이·혼잡도는 데이터로 확인할 수 없어요.</p>
    </section>

    <details class="basis small" @click.stop>
      <summary>판단 근거 보기</summary>
      <ul class="check-list">
        <li v-for="c in rec.checks" :key="c.criterion">
          <span class="pill" :class="resultClass(c.result)">{{ c.criterion }} {{ resultLabel(c.result) }}</span>
          {{ c.value }}<span v-if="c.basis" class="muted"> — {{ c.basis }}</span>
        </li>
      </ul>
      <p class="muted">추천 점수 {{ rec.score }} ({{ rec.score_reasons.join(', ') }}) · 출처 {{ sourceLabel(rec.source) }} #{{ rec.source_id }}</p>
    </details>
  </article>
</template>

<style scoped>
.rec { display: flex; flex-direction: column; gap: 12px; border-radius: 22px; padding: 18px; }
.rec-head { display: flex; gap: 12px; align-items: flex-start; }
.rank { width: 36px; height: 36px; flex: none; border-radius: 50% 50% 46% 46%; background: var(--accent); color: #fff;
  display: grid; place-items: center; font-weight: 700; font-family: 'Gowun Dodum', sans-serif; font-size: 18px; }
.title { flex: 1; min-width: 0; }
.title h3 { margin: 0; font-size: 19px; font-family: 'Gowun Dodum', sans-serif; }
.title p { margin: 2px 0 0; }
.save { flex: none; border-radius: 999px; }
.facts { display: flex; flex-wrap: wrap; gap: 6px; font-size: 13px; }
.fact { background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: 5px 10px; }
.fact.unknown { color: var(--warn); border-style: dashed; }
.fact.tag { background: var(--coffee-soft); border-color: transparent; color: var(--coffee); }
.menus { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.menu { background: var(--accent-soft); border-radius: 999px; padding: 6px 12px; font-size: 13px; }
.menu b { color: var(--accent); }
.no-menu { margin: 0; color: var(--muted); }
.checks { display: flex; flex-wrap: wrap; gap: 6px; }
.unverified { list-style: none; margin: 0; padding: 0; color: var(--warn); }
.cafes { background: var(--coffee-soft); border-radius: 16px; padding: 12px 14px; display: grid; gap: 6px; }
.cafes h4 { margin: 0; font-size: 13px; color: var(--coffee); font-weight: 500; }
.main-cafe { display: flex; gap: 10px; align-items: center; }
.cup { width: 34px; height: 34px; border-radius: 12px; background: #fff; display: grid; place-items: center; flex: none; }
.main-cafe a, .main-cafe strong { font-weight: 700; color: var(--coffee); }
.more summary, .basis summary { cursor: pointer; color: var(--muted); }
.more ul, .check-list { list-style: none; padding: 0; margin: 6px 0 0; display: grid; gap: 4px; }
.note { margin: 0; }
.cafe-facts { margin-top: 2px; }
.unknown { color: var(--warn); }
.map-btn { justify-self: start; border-radius: 999px; padding: 4px 12px; background: #fff; }
.main-cafe .map-btn { margin-left: auto; flex: none; }
.tiny { padding: 2px 10px; border-radius: 999px; font-size: 12px; margin-left: 6px; }
.btn:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
@media (max-width: 600px) { .rec-head { flex-wrap: wrap; } .save { width: 100%; } }
</style>
