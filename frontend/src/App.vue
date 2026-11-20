<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'

const publicDemo = import.meta.env.VITE_BABKAGONG_PUBLIC_DEMO === '1'
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <RouterLink to="/" class="brand">
        <span class="brand-mark">밥</span>
        <span class="brand-text">밥카공<small>밥 먹고 카공까지, 강남·역삼</small></span>
      </RouterLink>
      <nav class="nav">
        <RouterLink to="/" class="nav-link" exact-active-class="active">추천 대화</RouterLink>
        <RouterLink v-if="!publicDemo" to="/plans" class="nav-link" active-class="active">저장한 계획</RouterLink>
      </nav>
    </header>
    <main class="content">
      <p v-if="publicDemo" class="notice info">공개 데모에서는 코스 추천과 지도를 이용할 수 있어요. 계획 저장은 제공하지 않아요.</p>
      <RouterView />
    </main>
  </div>
</template>
