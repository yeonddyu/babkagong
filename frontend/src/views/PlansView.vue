<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, ApiError } from '../api'
import MapPanel from '../components/MapPanel.vue'
import type { Conflict, Plan, Recommendation } from '../types'

const route = useRoute()
const router = useRouter()
const plans = ref<Plan[]>([])
const filterDate = ref('')
const loading = ref(false)
const error = ref('')
const message = ref('')
const conflicts = ref<Conflict[]>([])
const editing = ref(false)
const form = ref<Partial<Plan>>({})

const selectedId = computed(() => (route.params.id ? Number(route.params.id) : null))
const selected = computed(() => plans.value.find((p) => p.id === selectedId.value) ?? null)
const hhmm = (t: string) => t.slice(0, 5)

// 저장한 코스를 지도에 다시 표시 (저장 당시 확인된 좌표가 있을 때만)
const planCourse = computed<Recommendation[] | null>(() => {
  const p = selected.value
  if (!p || p.restaurant_lat == null || p.restaurant_lng == null) return null
  return [{
    name: p.restaurant_name, source: p.restaurant_source ?? '', source_id: p.restaurant_source_id ?? '', address: p.restaurant_address,
    area: p.area, latitude: p.restaurant_lat, longitude: p.restaurant_lng, category: null, food_type: null, distance_m: null,
    estimated_walk_minutes: null, matched_menus: [], business_hours: null, checks: [], score: 0, score_reasons: [], unverified: [],
    cafes: p.cafe_name && p.cafe_lat != null && p.cafe_lng != null ? [{
      name: p.cafe_name, source: p.cafe_source ?? '', source_id: p.cafe_source_id ?? '', road_address: p.cafe_address, address: null,
      latitude: p.cafe_lat, longitude: p.cafe_lng, distance_m: null, distance_basis: null, estimated_walk_minutes: null,
      place_url: p.cafe_url, phone: null }] : [],
    cafe_notice: null,
  }]
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    plans.value = (await api.listPlans(filterDate.value || undefined)).plans
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '계획을 불러오지 못했어요.'
  } finally {
    loading.value = false
  }
}

function select(p: Plan) {
  editing.value = false
  conflicts.value = []
  message.value = ''
  router.push(`/plans/${p.id}`)
}

function startEdit() {
  if (!selected.value) return
  const p = selected.value
  form.value = { title: p.title, plan_date: p.plan_date, start_time: hhmm(p.start_time), end_time: hhmm(p.end_time),
                 restaurant_name: p.restaurant_name, cafe_name: p.cafe_name, memo: p.memo }
  editing.value = true
}

async function saveEdit() {
  if (!selected.value) return
  error.value = ''
  try {
    const res = await api.updatePlan(selected.value.id, form.value)
    conflicts.value = res.conflicts
    message.value = '수정했어요.'
    editing.value = false
    await load() // 목록에 바로 반영
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '수정하지 못했어요.'
  }
}

async function remove(p: Plan) {
  if (!confirm(`'${p.title}' 계획을 삭제할까요?`)) return
  try {
    await api.deletePlan(p.id)
    message.value = '삭제했어요.'
    conflicts.value = []
    await load()
    router.push('/plans')
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '삭제하지 못했어요.'
  }
}

watch(filterDate, load)
onMounted(load)
</script>

<template>
  <section class="plans">
    <div class="list card">
      <div class="list-head">
        <h2>저장한 계획</h2>
        <label class="field">날짜<input v-model="filterDate" type="date" aria-label="날짜 필터" /></label>
      </div>
      <p v-if="loading" class="muted small">불러오는 중…</p>
      <p v-else-if="!plans.length" class="muted small">저장한 계획이 없어요. 추천 대화에서 ‘이 코스 저장’을 눌러 보세요.</p>
      <ul>
        <li v-for="p in plans" :key="p.id" :class="{ on: p.id === selectedId }" @click="select(p)">
          <div class="when">{{ p.plan_date }} <b>{{ hhmm(p.start_time) }}~{{ hhmm(p.end_time) }}</b></div>
          <div class="what">{{ p.title }}</div>
        </li>
      </ul>
    </div>

    <div class="detail card">
      <div v-if="error" class="notice bad">{{ error }}</div>
      <div v-if="message" class="notice info">{{ message }}</div>
      <div v-if="conflicts.length" class="notice warn">
        ⚠ 같은 날 시간이 겹치는 계획이 있어요 (저장은 완료):
        <span v-for="c in conflicts" :key="c.id"> {{ c.title }}({{ hhmm(c.start_time) }}~{{ hhmm(c.end_time) }})</span>
      </div>

      <p v-if="!selected" class="muted">왼쪽 목록에서 계획을 고르면 상세 내용을 볼 수 있어요.</p>

      <template v-else-if="!editing">
        <h2>{{ selected.title }}</h2>
        <dl>
          <dt>날짜·시각</dt><dd>{{ selected.plan_date }} {{ hhmm(selected.start_time) }}~{{ hhmm(selected.end_time) }}</dd>
          <dt>지역</dt><dd>{{ selected.area ?? '-' }}</dd>
          <dt>식당</dt><dd>{{ selected.restaurant_name }} <span class="muted small">{{ selected.restaurant_address }}</span></dd>
          <dt>카페</dt>
          <dd>
            <a v-if="selected.cafe_url" :href="selected.cafe_url" target="_blank" rel="noopener">{{ selected.cafe_name }}</a>
            <span v-else>{{ selected.cafe_name ?? '-' }}</span>
            <span class="muted small"> {{ selected.cafe_address }}</span>
          </dd>
          <dt>메모</dt><dd>{{ selected.memo || '-' }}</dd>
          <dt>지도</dt>
          <dd>
            <MapPanel v-if="planCourse" :key="selected.id" class="plan-map" :recommendations="planCourse" :selected="0" :interactive="false" />
            <span v-else class="muted small">저장 당시 좌표가 없어 지도로 보여 줄 수 없어요 (이전에 저장한 계획)</span>
          </dd>
          <dt>생성</dt><dd class="small">{{ selected.created_at.slice(0, 16).replace('T', ' ') }}</dd>
          <dt>수정</dt><dd class="small">{{ selected.updated_at.slice(0, 16).replace('T', ' ') }}</dd>
        </dl>
        <div class="actions">
          <button class="btn primary" @click="startEdit">수정</button>
          <button class="btn danger" @click="remove(selected)">삭제</button>
        </div>
      </template>

      <form v-else class="edit" @submit.prevent="saveEdit">
        <label class="field">제목<input v-model="form.title" required maxlength="100" /></label>
        <label class="field">날짜<input v-model="form.plan_date" type="date" required /></label>
        <div class="row">
          <label class="field">시작<input v-model="form.start_time" type="time" required /></label>
          <label class="field">종료<input v-model="form.end_time" type="time" required /></label>
        </div>
        <label class="field">식당<input v-model="form.restaurant_name" required /></label>
        <label class="field">카페<input v-model="form.cafe_name" /></label>
        <label class="field">메모<textarea v-model="form.memo" rows="3" maxlength="1000" /></label>
        <div class="actions">
          <button class="btn primary" type="submit">저장</button>
          <button class="btn" type="button" @click="editing = false">취소</button>
        </div>
      </form>
    </div>
  </section>
</template>

<style scoped>
.plans { display: grid; grid-template-columns: 320px 1fr; gap: 16px; align-items: start; }
.list-head { display: flex; justify-content: space-between; align-items: end; gap: 8px; }
.list h2, .detail h2 { font-family: 'Gowun Dodum', sans-serif; margin: 0; }
.list ul { list-style: none; padding: 0; margin: 12px 0 0; display: grid; gap: 6px; }
.list li { padding: 10px 12px; border-radius: 10px; border: 1px solid var(--line); cursor: pointer; background: #fff; }
.list li.on { border-color: var(--accent); background: var(--accent-soft); }
.when { font-size: 13px; color: var(--muted); }
.what { font-weight: 500; }
.detail { display: grid; gap: 12px; }
dl { display: grid; grid-template-columns: 80px 1fr; gap: 8px; margin: 0; }
dt { color: var(--muted); font-size: 13px; }
dd { margin: 0; }
.actions { display: flex; gap: 8px; }
.plan-map { --map-h: 260px; }
.edit { display: grid; gap: 10px; }
.row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
@media (max-width: 760px) { .plans { grid-template-columns: 1fr; } }
</style>
